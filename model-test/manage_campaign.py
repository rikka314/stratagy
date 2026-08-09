from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = WORKSPACE_ROOT.parent
for candidate in (str(WORKSPACE_ROOT), str(REPO_ROOT)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from model_test.campaign import (
    load_campaign_snapshot,
    request_pause,
    resume_campaign,
    run_campaign_worker,
    start_campaign,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage the local Window 3B full research campaign.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("start", "pause", "resume", "status", "worker"):
        subparser = subparsers.add_parser(command)
        if command != "start":
            subparser.add_argument("--campaign-id", required=True)
        else:
            subparser.add_argument("--campaign-id")
    args = parser.parse_args(argv)

    if args.command == "start":
        snapshot = start_campaign(args.campaign_id)
    elif args.command == "pause":
        snapshot = request_pause(args.campaign_id)
    elif args.command == "resume":
        snapshot = resume_campaign(args.campaign_id)
    elif args.command == "status":
        snapshot = load_campaign_snapshot(args.campaign_id)
    else:
        return run_campaign_worker(args.campaign_id)

    print(json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

