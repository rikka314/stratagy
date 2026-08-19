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
from model_test.dynamic_ensemble_v2 import materialize_dynamic_ensemble_v2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Train and evaluate the research-only Phase-D uncertainty- and risk-aware dynamic ensemble."
    )
    parser.add_argument("--config", required=True, help="Path to moe_v2_us.json or moe_v2_cn_a.json")
    parser.add_argument("--output-dir", help="Optional output directory override")
    args = parser.parse_args(argv)
    try:
        outputs = materialize_dynamic_ensemble_v2(args.config, repo_root=REPO_ROOT, output_dir=args.output_dir)
    except DynamicEnsembleError as exc:
        print(f"Phase-D dynamic ensemble failed: {exc}", file=sys.stderr)
        return 2
    for name, path in outputs.items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
