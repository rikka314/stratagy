"""Reproducible, non-gating performance samples for the Strategy Lab app."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from statistics import median
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
IMPORT_APP_COMMAND = "import app"
IMPORT_APP_BUDGET_MS = 1_000.0


def percentile(values: list[float], fraction: float) -> float:
    """Return a linearly interpolated percentile for a non-empty sample."""
    ordered_values = sorted(values)
    if not ordered_values:
        raise ValueError("values must not be empty")
    if len(ordered_values) == 1:
        return ordered_values[0]

    index = (len(ordered_values) - 1) * fraction
    lower_index = int(index)
    upper_index = min(lower_index + 1, len(ordered_values) - 1)
    remainder = index - lower_index
    return ordered_values[lower_index] + (ordered_values[upper_index] - ordered_values[lower_index]) * remainder


def summarize_samples(samples_ms: list[float], *, budget_ms: float | None = None) -> dict[str, Any]:
    """Summarize samples without making host-specific budgets a hard gate."""
    if not samples_ms:
        raise ValueError("samples_ms must not be empty")

    summary: dict[str, Any] = {
        "samples_ms": samples_ms,
        "sample_count": len(samples_ms),
        "p50_ms": round(median(samples_ms), 3),
        "p75_ms": round(percentile(samples_ms, 0.75), 3),
    }
    if budget_ms is not None:
        summary["budget_ms"] = budget_ms
        summary["within_budget"] = summary["p75_ms"] <= budget_ms
    return summary


def _redact_diagnostic(value: str) -> str:
    redacted = re.sub(r"(?i)(api[_-]?key|token|password|secret)=([^\s&]+)", r"\1=<redacted>", value)
    return redacted[:240]


def _failure_summary(*, returncode: int | None, stderr: str = "", error_type: str | None = None) -> str:
    if error_type:
        return error_type
    return f"subprocess exited with code {returncode}: {_redact_diagnostic(stderr.strip())}"[:300]


def _measurement_environment() -> dict[str, str]:
    allowed_names = {
        "APPDATA",
        "HOMEDRIVE",
        "HOMEPATH",
        "LOCALAPPDATA",
        "PATH",
        "PATHEXT",
        "PROGRAMDATA",
        "PROGRAMFILES",
        "SYSTEMROOT",
        "SYSTEMDRIVE",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "PYTHONPATH",
    }
    environment = {key: value for key, value in os.environ.items() if key in allowed_names}
    environment["STRATAGY_PERF_TRACE"] = "0"
    environment["STRATAGY_PERF_IMPORT_PROBE"] = "1"
    return environment


def measure_import_app(*, samples: int) -> dict[str, Any]:
    """Measure fresh interpreter imports so each sample includes cold imports."""
    durations_ms: list[float] = []
    failures: list[str] = []
    for _ in range(samples):
        started_at = time.perf_counter()
        try:
            result = subprocess.run(
                [sys.executable, "-c", IMPORT_APP_COMMAND],
                cwd=PROJECT_ROOT,
                env=_measurement_environment(),
                capture_output=True,
                text=True,
                timeout=90,
                check=False,
                encoding="utf-8",
                errors="replace",
            )
        except subprocess.TimeoutExpired:
            durations_ms.append((time.perf_counter() - started_at) * 1000)
            failures.append(_failure_summary(returncode=None, error_type="TimeoutExpired"))
            continue
        except OSError as exc:
            durations_ms.append((time.perf_counter() - started_at) * 1000)
            failures.append(_failure_summary(returncode=None, error_type=type(exc).__name__))
            continue

        durations_ms.append((time.perf_counter() - started_at) * 1000)
        if result.returncode != 0:
            failures.append(_failure_summary(returncode=result.returncode, stderr=result.stderr))

    result_summary = summarize_samples(durations_ms, budget_ms=IMPORT_APP_BUDGET_MS)
    result_summary["command"] = f'{sys.executable} -c "{IMPORT_APP_COMMAND}"'
    result_summary["failures"] = failures
    return result_summary


def _apptest_error(app_test: Any) -> str | None:
    exception = getattr(app_test, "exception", None)
    if exception:
        return type(exception).__name__
    return None


def measure_apptest() -> dict[str, Any]:
    """Measure AppTest cold and same-process warm execution when it is available."""
    try:
        from streamlit.testing.v1 import AppTest
    except ImportError as exc:
        return {"status": "unavailable", "reason": str(exc)}

    app_path = PROJECT_ROOT / "app.py"
    root_path = str(PROJECT_ROOT)
    if root_path not in sys.path:
        sys.path.insert(0, root_path)
    try:
        app_test = AppTest.from_file(str(app_path))
        cold_started_at = time.perf_counter()
        app_test.run(timeout=90)
        cold_ms = (time.perf_counter() - cold_started_at) * 1000
        cold_error = _apptest_error(app_test)
        if cold_error:
            return {"status": "error", "cold_error": cold_error}

        warm_started_at = time.perf_counter()
        app_test.run(timeout=90)
        warm_ms = (time.perf_counter() - warm_started_at) * 1000
        warm_error = _apptest_error(app_test)
        if warm_error:
            return {"status": "error", "cold_execution": summarize_samples([cold_ms]), "warm_error": warm_error}
    except Exception as exc:  # AppTest surfaces application-specific dependency failures.
        return {"status": "error", "reason": type(exc).__name__}

    return {
        "status": "ok",
        "cold_execution": summarize_samples([cold_ms]),
        "warm_execution": summarize_samples([warm_ms]),
    }


def build_report(*, samples: int, include_apptest: bool) -> dict[str, Any]:
    """Build JSON for Python, Streamlit, and explicitly unmeasured browser layers."""
    streamlit_results: dict[str, Any] = measure_apptest() if include_apptest else {}
    return {
        "schema_version": 1,
        "layers": {
            "python": {"import_app": measure_import_app(samples=samples)},
            "streamlit": streamlit_results,
            "browser": {
                "status": "not_measured",
                "reason": "Use the Phase 0 Playwright procedure for browser timing.",
            },
        },
    }


def report_has_probe_failure(report: dict[str, Any]) -> bool:
    import_failures = report["layers"]["python"]["import_app"].get("failures", [])
    streamlit_status = report["layers"]["streamlit"].get("status")
    return bool(import_failures) or streamlit_status == "error"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=3, help="Fresh interpreter samples for import app (default: 3).")
    parser.add_argument("--skip-apptest", action="store_true", help="Skip Streamlit AppTest cold/warm execution.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.samples < 1:
        raise SystemExit("--samples must be at least 1")
    report = build_report(samples=args.samples, include_apptest=not args.skip_apptest)
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 2 if report_has_probe_failure(report) else 0


if __name__ == "__main__":
    raise SystemExit(main())
