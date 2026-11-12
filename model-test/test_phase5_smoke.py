"""Quick Phase 5 smoke test - validate advisory framework with minimal data."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.composite_advisory_cn_a import (
    CNAdvisoryConfig,
    CNCompositeAdvisory,
    decide_frame,
)


def create_test_data(n_rows: int = 100) -> pd.DataFrame:
    """Create synthetic test data for advisory."""
    np.random.seed(42)

    dates = pd.date_range("2023-01-01", periods=n_rows, freq="D")
    symbols = ["600519", "000858", "600036"] * (n_rows // 3 + 1)
    symbols = symbols[:n_rows]

    data = {
        "date": dates,
        "symbol": symbols,
        "composite_score": np.random.randn(n_rows) * 0.5,
        "composite_base_position": np.random.uniform(0.3, 0.8, n_rows),
        "mom_long_z": np.random.randn(n_rows),
        "rsi_z": np.random.randn(n_rows),
        "rel_strength_market": np.random.uniform(-0.1, 0.1, n_rows),
        "market_vol_level": np.random.uniform(0.1, 0.3, n_rows),
    }

    return pd.DataFrame(data)


def compute_metrics(decisions_df: pd.DataFrame) -> dict:
    """Compute simple metrics from decisions."""
    if decisions_df.empty:
        return {}

    return {
        "avg_base_position": decisions_df["composite_base_position"].mean(),
        "avg_final_position": decisions_df["final_position"].mean(),
        "avg_multiplier": decisions_df["advisory_multiplier"].mean(),
        "avg_reduction": (
            decisions_df["composite_base_position"] - decisions_df["final_position"]
        ).mean(),
        "fallback_rate": decisions_df["fallback_used"].sum() / len(decisions_df),
        "n_decisions": len(decisions_df),
    }


def main():
    print("=" * 60)
    print("Phase 5 Smoke Test - Advisory Framework Validation")
    print("=" * 60)

    # Create test data
    print("\n1. Creating test data...")
    test_data = create_test_data(n_rows=100)
    print(f"   Created {len(test_data)} test rows")

    # Setup config
    print("\n2. Setting up advisory config...")
    config = CNAdvisoryConfig(
        trend_trigger=0.50,
        trend_conflict_multiplier=0.75,
        reversion_trigger=0.65,
        reversion_multiplier=0.70,
        relative_trigger=0.30,
        relative_conflict_multiplier=0.75,
        macro_cap_floor=0.25,
    )
    print("   Config created")

    # Test policies
    policies = [
        "composite_only",
        "composite_plus_trend",
        "composite_plus_reversion",
        "composite_plus_relative_strength",
        "composite_plus_macro_cap",
        "composite_plus_all_advisories",
        "cash",
    ]

    print(f"\n3. Testing {len(policies)} policies...")
    results = {}

    for policy in policies:
        print(f"   - {policy}...", end=" ")
        decisions = decide_frame(test_data, policy=policy, config=config)
        metrics = compute_metrics(decisions)
        results[policy] = metrics
        print(f"OK ({metrics['n_decisions']} decisions)")

    # Display results
    print("\n4. Results Summary:")
    print("\n{:<40} {:<15} {:<15} {:<15} {:<15}".format(
        "Policy", "Avg Base", "Avg Final", "Avg Reduction", "Fallback Rate"
    ))
    print("-" * 100)

    for policy, metrics in results.items():
        if metrics:
            print("{:<40} {:<15.4f} {:<15.4f} {:<15.4f} {:<15.4f}".format(
                policy,
                metrics["avg_base_position"],
                metrics["avg_final_position"],
                metrics["avg_reduction"],
                metrics["fallback_rate"],
            ))

    # Validation checks
    print("\n5. Validation Checks:")
    checks_passed = 0
    checks_total = 0

    # Check 1: composite_only should not reduce position
    checks_total += 1
    composite_only_reduction = results["composite_only"]["avg_reduction"]
    if abs(composite_only_reduction) < 0.01:
        print("   [PASS] composite_only has no reduction")
        checks_passed += 1
    else:
        print(f"   [FAIL] composite_only reduction: {composite_only_reduction:.4f}")

    # Check 2: cash should zero out position
    checks_total += 1
    cash_final = results["cash"]["avg_final_position"]
    if cash_final < 0.01:
        print("   [PASS] cash policy zeros position")
        checks_passed += 1
    else:
        print(f"   [FAIL] cash final position: {cash_final:.4f}")

    # Check 3: all_advisories should reduce more than any single advisory
    checks_total += 1
    all_reduction = results["composite_plus_all_advisories"]["avg_reduction"]
    single_reductions = [
        results["composite_plus_trend"]["avg_reduction"],
        results["composite_plus_reversion"]["avg_reduction"],
        results["composite_plus_relative_strength"]["avg_reduction"],
        results["composite_plus_macro_cap"]["avg_reduction"],
    ]
    if all_reduction >= max(single_reductions):
        print("   [PASS] all_advisories reduces at least as much as any single advisory")
        checks_passed += 1
    else:
        print(f"   [FAIL] all_advisories reduction: {all_reduction:.4f}, max single: {max(single_reductions):.4f}")

    # Check 4: no fallbacks in this clean test data
    checks_total += 1
    max_fallback = max(r["fallback_rate"] for r in results.values() if r)
    if max_fallback < 0.01:
        print("   [PASS] No fallbacks with clean test data")
        checks_passed += 1
    else:
        print(f"   [FAIL] Max fallback rate: {max_fallback:.4f}")

    # Check 5: final <= base always
    checks_total += 1
    all_valid_bounds = True
    for policy, metrics in results.items():
        if policy != "cash" and metrics["avg_final_position"] > metrics["avg_base_position"]:
            all_valid_bounds = False
            print(f"   [FAIL] {policy}: final > base")
            break
    if all_valid_bounds:
        print("   [PASS] final_position <= base_position for all policies")
        checks_passed += 1

    # Final summary
    print("\n" + "=" * 60)
    print(f"Validation: {checks_passed}/{checks_total} checks passed")

    if checks_passed == checks_total:
        print("Status: [OK] Phase 5 framework validated successfully")
        print("\nNext step: Run full Phase 5 with real Phase 4 baseline data")
        return 0
    else:
        print("Status: [WARN] Some validation checks failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
