from __future__ import annotations

import argparse
import sys
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = WORKSPACE_ROOT.parent

for candidate in (str(WORKSPACE_ROOT), str(REPO_ROOT)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)


from model_test.admission import AdmissionEvidenceError, build_w11_admission_evidence, write_w11_admission_evidence


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build source-locked W11 admission evidence from Phase-B and Phase-D artifacts.")
    parser.add_argument("--panel-dir", required=True, help="Phase-B output directory")
    parser.add_argument("--phase-d-dir", required=True, help="Phase-D output directory")
    parser.add_argument("--output-dir", required=True, help="New evidence-only output directory")
    parser.add_argument("--candidate-variant", default="moe_v2_regime_aware")
    parser.add_argument("--required-splits", type=int, default=4)
    parser.add_argument("--minimum-not-worse-windows", type=int, default=3)
    parser.add_argument("--turnover-limit", type=float, default=1.25)
    args = parser.parse_args(argv)
    try:
        summary, breadth, decision = build_w11_admission_evidence(
            panel_dir=args.panel_dir,
            phase_d_dir=args.phase_d_dir,
            candidate_variant=args.candidate_variant,
            required_splits=args.required_splits,
            minimum_not_worse_windows=args.minimum_not_worse_windows,
            turnover_limit=args.turnover_limit,
        )
        outputs = write_w11_admission_evidence(
            args.output_dir,
            split_summary=summary,
            breadth=breadth,
            decision=decision,
        )
    except AdmissionEvidenceError as exc:
        print(f"W11 admission evidence failed: {exc}", file=sys.stderr)
        return 2
    for name, path in outputs.items():
        print(f"{name}: {path}")
    print(f"status: {decision['status']}")
    return 0 if decision["status"] == "admitted" else 3


if __name__ == "__main__":
    raise SystemExit(main())
