from __future__ import annotations

import argparse
import sys
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = WORKSPACE_ROOT.parent

for candidate in (str(WORKSPACE_ROOT), str(REPO_ROOT)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)


from model_test.moe_baseline import MoEBaselineError, materialize_phase_a_baseline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Freeze Phase-A dynamic-ensemble baselines from completed research runs.")
    parser.add_argument("--config", required=True, help="Path to moe_baseline_us.json or moe_baseline_cn_a.json")
    parser.add_argument("--output-dir", help="Optional output directory override")
    parser.add_argument(
        "--allow-pending",
        action="store_true",
        help="Write an explicit pending manifest and unavailable result rows when source outputs are absent",
    )
    args = parser.parse_args(argv)
    try:
        outputs = materialize_phase_a_baseline(
            args.config,
            repo_root=REPO_ROOT,
            output_dir=args.output_dir,
            allow_pending=args.allow_pending,
        )
    except MoEBaselineError as exc:
        print(f"Phase-A baseline failed: {exc}", file=sys.stderr)
        return 2
    for name, path in outputs.items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
