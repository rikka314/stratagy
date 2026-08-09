"""Opt-in, privacy-safe performance telemetry for Strategy Lab."""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from time import perf_counter
from typing import Any


TRACE_ENV_VAR = "STRATAGY_PERF_TRACE"
_EVENT_NAME = "stratagy.performance"
_SAFE_FIELD_NAMES = frozenset({
    "cache",
    "chart_key",
    "count",
    "has_focus_stock",
    "indicator_view",
    "market",
    "period_key",
    "section",
    "source",
    "status",
})


def is_performance_tracing_enabled() -> bool:
    """Return whether opt-in performance tracing is enabled for this process."""
    return os.getenv(TRACE_ENV_VAR, "").strip().lower() in {"1", "true", "yes", "on"}


def _safe_metadata(metadata: dict[str, Any]) -> dict[str, str | int | float | bool]:
    return {
        key: value
        for key, value in metadata.items()
        if key in _SAFE_FIELD_NAMES and isinstance(value, (str, int, float, bool))
    }


def _safe_dimension(value: str, *, fallback: str) -> str:
    normalized = str(value).strip()
    if not normalized or len(normalized) > 64 or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for char in normalized):
        return fallback
    return normalized


def emit_performance_event(
    route: str,
    phase: str,
    elapsed_ms: float,
    *,
    status: str = "ok",
    **metadata: Any,
) -> None:
    """Emit one JSON line, while never affecting application behavior."""
    if not is_performance_tracing_enabled():
        return

    payload: dict[str, Any] = {
        "event": _EVENT_NAME,
        "route": _safe_dimension(route, fallback="unknown"),
        "phase": _safe_dimension(phase, fallback="unknown"),
        "elapsed_ms": round(max(0.0, elapsed_ms), 3),
        "status": _safe_dimension(status, fallback="unknown"),
    }
    payload.update(_safe_metadata(metadata))
    try:
        print(json.dumps(payload, ensure_ascii=True, sort_keys=True), file=sys.stderr, flush=True)
    except (OSError, UnicodeError, ValueError):
        return


@contextmanager
def performance_span(route: str, phase: str, **metadata: Any) -> Iterator[None]:
    """Measure one synchronous boundary without changing its return or errors."""
    if not is_performance_tracing_enabled():
        yield
        return

    started_at = perf_counter()
    try:
        yield
    except BaseException:
        try:
            emit_performance_event(
                route,
                phase,
                (perf_counter() - started_at) * 1000,
                status="error",
                **metadata,
            )
        finally:
            raise
    else:
        emit_performance_event(route, phase, (perf_counter() - started_at) * 1000, **metadata)
