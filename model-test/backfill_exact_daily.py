from __future__ import annotations

import argparse
import sys
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = WORKSPACE_ROOT.parent
for candidate in (str(WORKSPACE_ROOT), str(REPO_ROOT)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)


from model_test.exact_daily_replay import (
    ExactDailyReplayError,
    backfill_exact_daily_artifacts,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Backfill exact daily US expert artifacts from frozen main-window parameters."
    )
    parser.add_argument("--config", required=True, help="Authoritative full-run config")
    parser.add_argument("--source-output-dir", required=True, help="Frozen full-run output directory")
    parser.add_argument("--scratch-output-dir", required=True, help="Separate replay scratch directory")
    parser.add_argument("--max-workers", type=int, default=1)
    args = parser.parse_args(argv)
    try:
        manifest, path = backfill_exact_daily_artifacts(
            args.config,
            repo_root=REPO_ROOT,
            source_output_dir=args.source_output_dir,
            scratch_output_dir=args.scratch_output_dir,
            max_workers=args.max_workers,
        )
    except (ExactDailyReplayError, OSError, ValueError) as exc:
        print(f"Exact daily backfill failed: {exc}", file=sys.stderr)
        return 2
    print(f"manifest: {path}")
    print(f"status: {manifest['status']}")
    print(f"artifacts: {manifest['artifact_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
