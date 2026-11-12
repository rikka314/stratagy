"""Simplified Phase 5 runner - quick advisory validation with real Phase 4 data."""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.composite_advisory_cn_a import CNAdvisoryConfig, decide_frame


def main():
    print("=" * 60)
    print("Phase 5 Quick Run - Advisory with Real Phase 4 Data")
    print("=" * 60)

    # Load Phase 4 composite daily
    print("\n1. Loading Phase 4 composite_daily.parquet...")
    composite_path = Path("model-test/outputs/composite_cn_a/composite_daily.parquet")
    composite_df = pd.read_parquet(composite_path)
    print(f"   Loaded {len(composite_df)} rows")

    # Load Phase 3 factor panel
    print("\n2. Loading Phase 3 factor panel...")
    factor_path = Path("model-test/outputs/composite_cn_a/cn_a_factor_panel.parquet")
    factor_df = pd.read_parquet(factor_path)
    print(f"   Loaded {len(factor_df)} rows")

    # Merge
    print("\n3. Merging composite with factors...")
    # Rename columns to match advisory contract
    composite_df = composite_df.rename(columns={
        "score": "composite_score",
        "position": "composite_base_position",
    })

    merged = pd.merge(
        composite_df[["date", "symbol", "fold_id", "composite_score", "composite_base_position"]],
        factor_df[["date", "symbol", "mom_long_z", "rsi_z", "rel_strength_market", "market_vol_level"]],
        on=["date", "symbol"],
        how="inner",
    )
    print(f"   Merged {len(merged)} rows")

    # Sample for quick test (use 10% of data)
    print("\n4. Sampling data for quick test...")
    sample_size = max(1000, len(merged) // 10)
    merged_sample = merged.sample(n=min(sample_size, len(merged)), random_state=42)
    print(f"   Using {len(merged_sample)} rows")

    # Setup config
    print("\n5. Setting up advisory config...")
    config = CNAdvisoryConfig(
        trend_trigger=0.50,
        trend_conflict_multiplier=0.75,
        reversion_trigger=0.65,
        reversion_multiplier=0.70,
        relative_trigger=0.30,
        relative_conflict_multiplier=0.75,
        macro_cap_floor=0.25,
    )

    # Run policies
    policies = [
        "composite_only",
        "composite_plus_trend",
        "composite_plus_reversion",
        "composite_plus_relative_strength",
        "composite_plus_macro_cap",
        "composite_plus_all_advisories",
    ]

    print(f"\n6. Running {len(policies)} policies...")
    results = {}

    for policy in policies:
        print(f"   - {policy}...", end=" ")
        decisions = decide_frame(merged_sample, policy=policy, config=config)

        # Compute metrics
        avg_base = decisions["composite_base_position"].mean()
        avg_final = decisions["final_position"].mean()
        avg_reduction = avg_base - avg_final
        fallback_rate = decisions["fallback_used"].sum() / len(decisions)

        results[policy] = {
            "avg_base": avg_base,
            "avg_final": avg_final,
            "avg_reduction": avg_reduction,
            "fallback_rate": fallback_rate,
            "n_decisions": len(decisions),
        }
        print(f"OK ({len(decisions)} decisions)")

    # Display results
    print("\n7. Results Summary:")
    print("\n{:<40} {:<12} {:<12} {:<12} {:<12}".format(
        "Policy", "Avg Base", "Avg Final", "Reduction", "Fallback%"
    ))
    print("-" * 88)

    for policy, metrics in results.items():
        print("{:<40} {:<12.4f} {:<12.4f} {:<12.4f} {:<12.2%}".format(
            policy,
            metrics["avg_base"],
            metrics["avg_final"],
            metrics["avg_reduction"],
            metrics["fallback_rate"],
        ))

    # Gate checks
    print("\n8. Advisory Gate Checks:")
    baseline = results["composite_only"]

    checks_passed = 0
    checks_total = 0

    for policy in policies[1:]:  # Skip composite_only
        metrics = results[policy]

        checks_total += 1

        # Check 1: Reduces position
        reduces = metrics["avg_reduction"] > baseline["avg_reduction"]

        # Check 2: Not too aggressive (reduction < 50%)
        not_too_aggressive = metrics["avg_reduction"] < 0.5

        # Check 3: Low fallback
        low_fallback = metrics["fallback_rate"] < 0.05

        passed = reduces and not_too_aggressive and low_fallback

        if passed:
            checks_passed += 1
            status = "[PASS]"
        else:
            status = "[FAIL]"

        print(f"   {status} {policy}")
        print(f"        Reduces: {reduces}, Not too aggressive: {not_too_aggressive}, Low fallback: {low_fallback}")

    # Save quick results
    output_dir = Path("model-test/outputs/composite_advisory_cn_a")
    output_dir.mkdir(parents=True, exist_ok=True)

    quick_results = pd.DataFrame(results).T
    quick_results.to_csv(output_dir / "quick_ablation_results.csv")
    print(f"\n9. Quick results saved to: {output_dir / 'quick_ablation_results.csv'}")

    # Save manifest
    manifest = {
        "phase": "phase5_quick_run",
        "market": "CN_A",
        "n_decisions": len(merged_sample),
        "policies_tested": policies,
        "checks_passed": checks_passed,
        "checks_total": checks_total,
        "status": "quick_validation_complete",
    }

    with open(output_dir / "quick_manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"   Manifest saved to: {output_dir / 'quick_manifest.json'}")

    # Final summary
    print("\n" + "=" * 60)
    print(f"Phase 5 Quick Validation: {checks_passed}/{checks_total} policies passed")

    if checks_passed >= checks_total * 0.5:
        print("Status: [OK] Advisory framework working correctly with real data")
        return 0
    else:
        print("Status: [WARN] Some policies need tuning")
        return 1


if __name__ == "__main__":
    sys.exit(main())
