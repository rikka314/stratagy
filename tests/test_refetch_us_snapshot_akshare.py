"""Focused contract tests for the AkShare research snapshot adapter."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from refetch_us_snapshot_akshare import (
    AkShareProviderError,
    _load_symbol,
    _universe_fingerprint,
    _validate_source,
    refetch,
)


REQUIRED_COLUMNS = ["date", "open", "high", "low", "close", "volume"]


def _source(symbols: list[str]) -> dict[str, object]:
    return {
        "market": "US",
        "data": {
            "start": "2016-07-19",
            "end": "2026-08-07",
            "adjustment": "qfq",
        },
        "universe": {"symbols": symbols},
    }


def _frame(rows: int = 3_700) -> pd.DataFrame:
    dates = pd.date_range("2016-07-19", periods=rows, freq="D")
    return pd.DataFrame(
        {
            "date": dates,
            "open": 10.0,
            "high": 11.0,
            "low": 9.0,
            "close": 10.5,
            "volume": 1_000.0,
        }
    )


class _Ak:
    def __init__(self, frame: pd.DataFrame) -> None:
        self.frame = frame

    def stock_us_daily(self, *, symbol: str, adjust: str) -> pd.DataFrame:
        assert symbol == "AAPL"
        assert adjust == "qfq"
        return self.frame.copy()


class _FailAfterAapl:
    def stock_us_daily(self, *, symbol: str, adjust: str) -> pd.DataFrame:
        assert adjust == "qfq"
        if symbol == "AAPL":
            return _frame()
        raise RuntimeError("provider failure")


def test_load_symbol_rejects_missing_columns() -> None:
    frame = _frame().drop(columns=["volume"])
    with pytest.raises(AkShareProviderError, match="missing columns"):
        _load_symbol(_Ak(frame), "AAPL")


def test_load_symbol_rejects_malformed_dates_and_nonnumeric_values() -> None:
    malformed = _frame()
    malformed["date"] = malformed["date"].astype(object)
    malformed.loc[0, "date"] = "not-a-date"
    with pytest.raises(AkShareProviderError, match="malformed dates"):
        _load_symbol(_Ak(malformed), "AAPL")

    nonnumeric = _frame()
    nonnumeric["close"] = nonnumeric["close"].astype(object)
    nonnumeric.loc[0, "close"] = "N/A"
    with pytest.raises(AkShareProviderError, match="nonnumeric"):
        _load_symbol(_Ak(nonnumeric), "AAPL")


def test_load_symbol_rejects_duplicate_dates() -> None:
    duplicate = _frame()
    duplicate.loc[1, "date"] = duplicate.loc[0, "date"]
    with pytest.raises(AkShareProviderError, match="duplicate dates"):
        _load_symbol(_Ak(duplicate), "AAPL")


def test_refetch_success_writes_relative_manifest_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_path = tmp_path / "source.json"
    source_path.write_text(
        json.dumps(_source(["AAPL"])), encoding="utf-8"
    )
    output = tmp_path / "snapshot"
    monkeypatch.setattr("refetch_us_snapshot_akshare._validate_source", lambda *_: ["AAPL"])
    monkeypatch.setattr("refetch_us_snapshot_akshare._resolve_proxies", lambda: {})
    monkeypatch.setattr("refetch_us_snapshot_akshare._proxy_summary", lambda _: {"enabled": False})
    monkeypatch.setitem(__import__("sys").modules, "akshare", _Ak(_frame()))

    # The adapter imports the module object and calls its endpoint directly.
    manifest = refetch(source_path, output)

    assert manifest["data"]["adjustment"] == "qfq_akshare"
    assert manifest["universe"]["files"][0]["path"] == "data_snapshot/AAPL_daily.csv"
    assert manifest["universe"]["fingerprint"] == _universe_fingerprint(["AAPL"])
    assert (output / "data_snapshot" / "AAPL_daily.csv").is_file()
    assert not Path(manifest["universe"]["files"][0]["path"]).is_absolute()


def test_refetch_failure_after_success_does_not_leave_partial_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_path = tmp_path / "source.json"
    source_path.write_text(json.dumps(_source(["AAPL", "MSFT"])), encoding="utf-8")
    output = tmp_path / "snapshot"
    monkeypatch.setattr(
        "refetch_us_snapshot_akshare._validate_source", lambda *_: ["AAPL", "MSFT"]
    )
    monkeypatch.setitem(__import__("sys").modules, "akshare", _FailAfterAapl())

    with pytest.raises(RuntimeError, match="one or more symbols failed"):
        refetch(source_path, output)
    assert not output.exists()


def test_refetch_failure_does_not_leave_partial_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_path = tmp_path / "source.json"
    source_path.write_text(json.dumps(_source(["AAPL"])), encoding="utf-8")
    output = tmp_path / "snapshot"
    monkeypatch.setattr("refetch_us_snapshot_akshare._validate_source", lambda *_: ["AAPL"])
    monkeypatch.setitem(__import__("sys").modules, "akshare", _Ak(_frame().iloc[:10]))

    with pytest.raises(RuntimeError, match="data quality audit failed"):
        refetch(source_path, output)
    assert not output.exists()
