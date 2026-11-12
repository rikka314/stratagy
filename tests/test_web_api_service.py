from __future__ import annotations

import pandas as pd
import pytest
from pydantic import ValidationError

from api.models import PortfolioRequest, StockLoadRequest
from api.storage import ApiStorage
from api.service import control_experiment, prepare_dataframe, run_portfolio_calculation, run_single_calculation, validated_params
from api.session import request_session_state
from ui.single_stock_workflow import StrategyRequest, build_strategy_context_key, freeze_params_snapshot, run_strategy_pipeline


@pytest.fixture(scope="module")
def market_frame() -> pd.DataFrame:
    return prepare_dataframe(pd.read_csv("data/aapl_clean_daily.csv").tail(700))


def _dataset(frame: pd.DataFrame, symbol: str = "AAPL") -> dict:
    return {"symbol": symbol, "market": "US", "adjust": "qfq", "source": "upload", "dataframe": frame.copy()}


@pytest.mark.parametrize("request_payload", [
    {"family": "baseline", "baseline_kind": "naive"},
    {"family": "search", "search_base": "sm"},
])
def test_api_single_calculation_matches_existing_workflow(market_frame: pd.DataFrame, request_payload: dict) -> None:
    dataset = _dataset(market_frame)
    api_result = run_single_calculation(dataset, request_payload, {}, 0.7)

    params = validated_params({})
    request = StrategyRequest(**request_payload)
    context_key = build_strategy_context_key(
        market="US", symbol="AAPL", adjust="qfq", df_raw=market_frame,
        train_ratio=0.7, uploaded_file=object(),
    )
    with request_session_state():
        direct = run_strategy_pipeline(
            context_key=context_key, request=request, request_params_snapshot=freeze_params_snapshot(params),
            df_raw=market_frame, split_idx=int(len(market_frame) * 0.7), symbol="AAPL", market="US", adjust="qfq",
        )

    assert direct.artifact is not None
    assert api_result["status"] == direct.status
    assert api_result["artifact"]["metrics"] == direct.artifact.eval
    assert api_result["artifact"]["returns"][-1]["return"] == pytest.approx(float(direct.artifact.returns_series.iloc[-1]))


def test_request_session_state_isolated() -> None:
    with request_session_state({"value": 1}) as first:
        first["changed"] = True
    with request_session_state({"value": 2}) as second:
        assert second == {"value": 2}


def test_portfolio_uses_real_core_calculation(market_frame: pd.DataFrame) -> None:
    second = market_frame.copy()
    second["close"] = second["close"] * 1.015
    second["open"] = second["open"] * 1.015
    second["high"] = second["high"] * 1.015
    second["low"] = second["low"] * 1.015
    first_dataset = {**_dataset(market_frame), "dataset_id": "a" * 24}
    second_dataset = {**_dataset(second, "SECOND"), "dataset_id": "b" * 24}
    result = run_portfolio_calculation([first_dataset, second_dataset], {}, {"a" * 24: 0.6, "b" * 24: 0.4})
    assert set(result["individual"]) == {"AAPL", "SECOND"}
    assert result["equity"]
    assert result["metrics"]["sharpe"] is not None


def test_api_rejects_unknown_or_unsafe_params() -> None:
    with pytest.raises(ValueError, match="unsupported strategy params"):
        validated_params({"news_factor_path": "C:/secret.csv"})


def test_api_validates_symbols_weights_and_market_data(market_frame: pd.DataFrame) -> None:
    with pytest.raises(ValidationError):
        StockLoadRequest(symbol="../../secret", market="US")
    with pytest.raises(ValidationError):
        PortfolioRequest(dataset_ids=["a" * 20, "b" * 20], weights={"AAPL": float("nan")})

    broken = market_frame.copy()
    broken.loc[broken.index[-1], "high"] = broken.loc[broken.index[-1], "low"] - 1
    with pytest.raises(ValueError, match="inconsistent OHLC"):
        prepare_dataframe(broken)


def test_orphaned_persisted_job_is_marked_interrupted(tmp_path, monkeypatch) -> None:
    from api import main

    isolated = ApiStorage(tmp_path / "api")
    job_id = isolated.new_id()
    isolated.save_job(job_id, {"job_id": job_id, "runner_id": "old-process", "status": "running", "progress": 0.5})
    monkeypatch.setattr(main, "storage", isolated)

    restored = main._job_or_404(job_id)
    assert restored["status"] == "failed"
    assert "process restart" in restored["error"]


def test_research_control_is_disabled_without_local_flag(monkeypatch) -> None:
    monkeypatch.delenv("STRATAGY_RESEARCH_CONTROL", raising=False)
    with pytest.raises(PermissionError, match="disabled"):
        control_experiment("start", "test-campaign")


def test_portfolio_rejects_overflowing_weight_sum():
    with pytest.raises(ValidationError, match="finite positive sum"):
        PortfolioRequest(dataset_ids=["a" * 24, "b" * 24], weights={"ONE": 1e308, "TWO": 1e308})


def test_portfolio_rejects_silently_omitted_symbol(market_frame, monkeypatch):
    from api import service

    monkeypatch.setattr(service, "run_portfolio_simulation", lambda *args, **kwargs: {
        "individual_results": {"AAPL": {}, "SECOND": {}},
    })
    datasets = [_dataset(market_frame, symbol) for symbol in ["AAPL", "SECOND", "THIRD"]]
    with pytest.raises(ValueError, match="THIRD"):
        service.run_portfolio_calculation(datasets, {}, None)


def test_completed_portfolio_can_restore_without_recalculation(market_frame, tmp_path, monkeypatch):
    from api import main

    root = tmp_path / "api"
    store = ApiStorage(root)
    ids = [store.new_id(), store.new_id()]
    for dataset_id, symbol in zip(ids, ["AAPL", "SECOND"]):
        store.save_dataset(dataset_id, _dataset(market_frame, symbol))
    monkeypatch.setattr(main, "storage", store)
    result = main.portfolio(PortfolioRequest(dataset_ids=ids))
    monkeypatch.setattr(main, "storage", ApiStorage(root))
    monkeypatch.setattr(main, "run_portfolio_calculation", lambda *args: pytest.fail("restore must not recompute"))
    restored = main.portfolio_result(result["result_id"])
    assert restored["metrics"] == result["metrics"]
    assert restored["equity"] == result["equity"]
