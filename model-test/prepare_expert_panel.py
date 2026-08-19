from __future__ import annotations

import argparse
import sys
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = WORKSPACE_ROOT.parent

for candidate in (str(WORKSPACE_ROOT), str(REPO_ROOT)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)


from model_test.expert_panel import ExpertPanelError, materialize_expert_panel


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Materialize the leak-free Phase-B expert-day panel from a frozen Phase-A source run."
    )
    parser.add_argument("--config", required=True, help="Path to moe_baseline_us.json or moe_baseline_cn_a.json")
    parser.add_argument("--output-dir", help="Optional output directory override")
    parser.add_argument("--news-factor-path", help="Optional news factor CSV; values are aligned to the prior trading day")
    parser.add_argument("--market-context-path", help="Optional point-in-time market context CSV")
    parser.add_argument("--horizon-days", type=int, default=20, help="Primary future-label horizon (default: 20)")
    parser.add_argument("--lambda-downside", type=float, default=1.0)
    parser.add_argument("--lambda-turnover", type=float, default=0.1)
    parser.add_argument("--n-splits", type=int, help="Optional split count for configs without frozen phase_b.n_splits")
    parser.add_argument("--min-train-days", type=int)
    parser.add_argument("--validation-days", type=int)
    parser.add_argument("--test-days", type=int)
    parser.add_argument("--step-days", type=int)
    parser.add_argument("--embargo-days", type=int)
    parser.add_argument(
        "--allow-pending",
        action="store_true",
        help="Write an explicit pending panel when frozen source artifacts are unavailable",
    )
    args = parser.parse_args(argv)

    try:
        outputs = materialize_expert_panel(
            args.config,
            repo_root=REPO_ROOT,
            output_dir=args.output_dir,
            allow_pending=args.allow_pending,
            news_factor_path=args.news_factor_path,
            market_context_path=args.market_context_path,
            primary_horizon_days=args.horizon_days,
            lambda_downside=args.lambda_downside,
            lambda_turnover=args.lambda_turnover,
            n_splits=args.n_splits,
            min_train_days=args.min_train_days,
            validation_days=args.validation_days,
            test_days=args.test_days,
            step_days=args.step_days,
            embargo_days=args.embargo_days,
        )
    except ExpertPanelError as exc:
        print(f"Phase-B expert panel failed: {exc}", file=sys.stderr)
        return 2
    for name, path in outputs.items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
