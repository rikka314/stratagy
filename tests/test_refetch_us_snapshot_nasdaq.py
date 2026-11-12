"""Focused contract tests for the Nasdaq research snapshot adapter."""

from __future__ import annotations

import importlib
from pathlib import Path

import pandas as pd
import pytest

from refetch_us_snapshot_nasdaq import (
    NasdaqProviderError,
    _fetch_symbol,
    _parse_number,
    _validate_symbol,
    refetch,
)


class _Response:
    def __init__(self, status_code: int, payload: object) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> object:
        return self._payload


class _Session:
    def __init__(self, responses: list[_Response]) -> None:
        self.responses = iter(responses)
        self.calls = 0

    def get(self, *_args: object, **_kwargs: object) -> _Response:
        self.calls += 1
        return next(self.responses)


def _row(volume: str = "1,000") -> dict[str, str]:
    return {
        "date": "08/07/2026",
        "open": "$10.00",
        "high": "$11.00",
        "low": "$9.00",
        "close": "$10.50",
        "volume": volume,
    }


def test_validate_symbol_rejects_path_traversal() -> None:
    with pytest.raises(ValueError, match="invalid US symbol"):
        _validate_symbol("../../target")


def test_parse_number_handles_currency_and_rejects_missing_value() -> None:
    assert _parse_number("$1,234.50", "close", "AAPL") == pytest.approx(1234.5)
    with pytest.raises(NasdaqProviderError, match="invalid Nasdaq volume"):
        _parse_number("N/A", "volume", "SUZ")


def test_parse_number_rejects_fractional_volume() -> None:
    with pytest.raises(NasdaqProviderError, match="non-integer Nasdaq volume"):
        _parse_number("1000.5", "volume", "AAPL")


def test_fetch_symbol_retries_rate_limit_and_normalizes_rows() -> None:
    payload = {"data": {"tradesTable": {"rows": [_row()]}}}
    session = _Session([_Response(429, {}), _Response(200, payload)])

    frame = _fetch_symbol(session, "AAPL", "2016-07-19", "2026-08-07")

    assert session.calls == 2
    assert list(frame.columns) == ["date", "open", "high", "low", "close", "volume"]
    assert frame.iloc[0]["date"] == pd.Timestamp("2026-08-07").date()
    assert frame.iloc[0]["volume"] == 1000


def test_fetch_symbol_rejects_duplicate_dates() -> None:
    duplicate_rows = [_row(), _row()]
    payload = {"data": {"tradesTable": {"rows": duplicate_rows}}}
    with pytest.raises(NasdaqProviderError, match="duplicate dates"):
        _fetch_symbol(
            _Session([_Response(200, payload)]),
            "AAPL",
            "2016-07-19",
            "2026-08-07",
        )


def test_fetch_symbol_rejects_empty_response() -> None:
    payload = {"data": {"tradesTable": {"rows": []}}}
    with pytest.raises(NasdaqProviderError, match="no historical rows"):
        _fetch_symbol(_Session([_Response(200, payload)]), "AAPL", "2016-07-19", "2026-08-07")


def test_refetch_is_fail_closed_for_incomplete_universe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = {
        "market": "US",
        "data": {
            "start": "2016-07-19",
            "end": "2026-08-07",
            "adjustment": "qfq",
        },
        "universe": {"symbols": ["RUBI"]},
    }
    manifest_path = tmp_path / "source.json"
    manifest_path.write_text(__import__("json").dumps(source), encoding="utf-8")
    output_dir = tmp_path / "snapshot"

    with pytest.raises(ValueError, match="exactly 60"):
        refetch(manifest_path, output_dir, "2016-07-19", "2026-08-07")
    assert not output_dir.exists()


def test_nasdaq_adapter_does_not_change_yahoo_module() -> None:
    module = importlib.import_module("refetch_us_snapshot")
    assert module.DEFAULT_START == "2016-07-19"
    assert "qfq" in module.__doc__ or "yfinance" in module.__doc__
