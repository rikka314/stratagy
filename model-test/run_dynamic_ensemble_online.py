from __future__ import annotations

import argparse
import sys
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = WORKSPACE_ROOT.parent
for candidate in (str(WORKSPACE_ROOT), str(REPO_ROOT)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from model_test.dynamic_ensemble import DynamicEnsembleError
from model_test.dynamic_ensemble_online import materialize_online_ensemble


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Replay a frozen MoE and evaluate Phase-E Hedge / EG online expert weighting."
    )
    parser.add_argument("--config", required=True, help="Path to moe_online_us.json or moe_online_cn_a.json")
    parser.add_argument("--output-dir", help="Optional output directory override")
    args = parser.parse_args(argv)
    try:
        outputs = materialize_online_ensemble(args.config, repo_root=REPO_ROOT, output_dir=args.output_dir)
    except DynamicEnsembleError as exc:
        print(f"Phase-E online ensemble failed: {exc}", file=sys.stderr)
        return 2
    for name, path in outputs.items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
