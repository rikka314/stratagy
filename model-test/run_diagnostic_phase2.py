"""Phase 2 diagnostic runner for Transformer State v3.

This script executes the Phase 2 diagnostic analysis on Phase 1 baseline results.

Usage:
    python model-test/run_diagnostic_phase2.py --config model-test/configs/transformer_state_v3_us.json

The diagnostic will:
1. Decompose neighbor utility patterns by expert
2. Analyze sampling bias in Train memory
3. Recommend whether to proceed to Phase 3, stop, or refactor
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Add model-test to path
sys.path.insert(0, str(Path(__file__).parent))

from model_test.transformer_state_diagnostic import (
    DiagnosticConfig,
    run_phase2_diagnostic,
    save_diagnostic_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Phase 2 diagnostic for Transformer State v3"
    )
    parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Path to v3 config JSON",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Override output directory (default: from config)",
    )

    args = parser.parse_args()

    # Load config
    if not args.config.exists():
        print(f"Error: Config not found: {args.config}", file=sys.stderr)
        return 1

    with open(args.config) as f:
        config = json.load(f)

    # Resolve paths
    output_subdir = config.get("output_subdir", "transformer_state_v3_us")
    baseline_output_dir = Path(f"model-test/outputs/{output_subdir}/baseline_artifacts")

    if args.output_dir:
        output_dir = args.output_dir
    else:
        output_dir = Path(f"model-test/outputs/{output_subdir}")

    # Source panel from baseline config
    baseline_config = config.get("baseline", {})
    source_panel_dir = baseline_config.get("source_panel_output_dir")
    if not source_panel_dir:
        print("Error: baseline.source_panel_output_dir not in config", file=sys.stderr)
        return 1

    source_panel_path = Path(source_panel_dir) / "state_sequence_panel.parquet"
    if not source_panel_path.exists():
        print(f"Error: Source panel not found: {source_panel_path}", file=sys.stderr)
        return 1

    # Expert IDs
    expert_ids = tuple(config.get("experts", []))
    if not expert_ids:
        print("Error: No experts defined in config", file=sys.stderr)
        return 1

    print("=" * 80)
    print("Transformer State v3 - Phase 2 Diagnostic")
    print("=" * 80)
    print(f"Config: {args.config}")
    print(f"Baseline output: {baseline_output_dir}")
    print(f"Source panel: {source_panel_path}")
    print(f"Experts: {', '.join(expert_ids)}")
    print(f"Output: {output_dir}")
    print()

    # Verify baseline artifacts exist
    if not baseline_output_dir.exists():
        print(
            f"Error: Baseline artifacts not found at {baseline_output_dir}",
            file=sys.stderr,
        )
        print("Run Phase 1 first: python model-test/run_baseline_phase1.py --config <config>")
        return 1

    # Check for baseline comparison
    comparison_path = baseline_output_dir / "baseline_comparison.csv"
    if not comparison_path.exists():
        print(f"Error: Baseline comparison not found: {comparison_path}", file=sys.stderr)
        return 1

    # Create diagnostic config
    diagnostic_config = DiagnosticConfig(
        baseline_output_dir=baseline_output_dir,
        source_panel_path=source_panel_path,
        expert_ids=expert_ids,
        top_k=config.get("retrieval", {}).get("top_k", 15),
    )

    # Run diagnostic
    print("Running Phase 2 diagnostic...")
    print()

    try:
        result = run_phase2_diagnostic(diagnostic_config)
    except Exception as e:
        print(f"Error during diagnostic: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1

    # Save report
    report_dir = output_dir / "phase2_diagnostic"
    save_diagnostic_report(result, report_dir)

    # Print decision
    print()
    print("=" * 80)
    print("PHASE 2 DECISION")
    print("=" * 80)
    print(f"Recommendation: {result.decision_recommendation.upper()}")
    print()
    print(result.decision_rationale)
    print()
    print("=" * 80)

    # Print summary stats
    print()
    print("Summary Statistics:")
    for key, value in result.summary_stats.items():
        if key not in ["expert_details", "sampling_details"]:
            print(f"  {key}: {value}")

    print()
    print(f"Full report: {report_dir / 'phase2_diagnostic_report.md'}")
    print()

    # Next steps guidance
    print("Next Steps:")
    if result.decision_recommendation == "continue":
        print("  1. Proceed with full utility vector labels (L01)")
        print("  2. Optionally implement stride=5 sampling (S01)")
        print("  3. Train Transformer encoder (Phase 3)")
    elif result.decision_recommendation == "refactor":
        print("  1. Implement stride=5 sampling (S01)")
        print("  2. Re-run baselines with new sampling")
        print("  3. Re-run this diagnostic")
        print("  4. If diagnostic passes, proceed to Phase 3")
    else:  # stop
        print("  1. Do NOT proceed to Phase 3 Transformer training")
        print("  2. Consider using PCA baselines as primary method")
        print("  3. Document why state matching did not work")

    return 0


if __name__ == "__main__":
    sys.exit(main())
