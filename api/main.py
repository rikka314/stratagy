"""FastAPI entry point: ``uvicorn api.main:app``."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import re
import secrets
import os
from threading import Lock
from typing import Any

import pandas as pd
from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from core.data import get_stock_label_map, load_uploaded_bytes, search_stock_candidates
from core.utils import get_available_stocks, load_or_fetch_stock

from .models import CampaignStartRequest, DatasetAnalysisRequest, DatasetSliceRequest, PortfolioOptimizeRequest, PortfolioRequest, SingleJobRequest, StockLoadRequest
from .service import (
    control_experiment, dataset_summary, experiment_snapshots, final_report, normalize_market, optimize_portfolio,
    prepare_dataframe, research_catalog, research_report, run_portfolio_calculation,
    run_single_calculation, simple_report_html, single_export_html, utc_now,
)
from .storage import storage
from .home import router as home_router


API_PREFIX = "/strategy/api"
MAX_UPLOAD_BYTES = 12 * 1024 * 1024
MAX_PENDING_JOBS = 16
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="strategy-api")
_pending_jobs: set[str] = set()
_pending_lock = Lock()
_runner_id = secrets.token_urlsafe(12)

app = FastAPI(title="Strategy Lab API", version="1.0.0", docs_url=f"{API_PREFIX}/docs", openapi_url=f"{API_PREFIX}/openapi.json")
app.include_router(home_router, prefix=API_PREFIX)


def _dataset_or_404(dataset_id: str) -> dict[str, Any]:
    dataset = storage.load_dataset(dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="dataset not found or expired")
    return dataset


def _job_or_404(job_id: str) -> dict[str, Any]:
    job = storage.load_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found or expired")
    if job.get("status") in {"queued", "running"} and job.get("runner_id") != _runner_id:
        job.update({
            "status": "failed", "progress": 1.0, "finished_at": utc_now(),
            "error": "calculation was interrupted by an API process restart",
        })
        storage.save_job(job_id, job)
    return job


def _run_job(job_id: str, payload: dict[str, Any]) -> None:
    job = storage.load_job(job_id) or payload
    job.update({"status": "running", "progress": 0.15, "started_at": utc_now()})
    storage.save_job(job_id, job)
    try:
        dataset = _dataset_or_404(payload["dataset_id"])
        result = run_single_calculation(dataset, payload["request"], payload["params"], payload["train_ratio"])
        job.update({"status": "completed", "progress": 1.0, "finished_at": utc_now(), "result": result, "error": None})
    except Exception as exc:
        job.update({"status": "failed", "progress": 1.0, "finished_at": utc_now(), "error": str(exc)})
    storage.save_job(job_id, job)
    with _pending_lock:
        _pending_jobs.discard(job_id)


@app.get(f"{API_PREFIX}/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get(f"{API_PREFIX}/metadata")
def metadata() -> dict[str, Any]:
    from .service import default_params
    return {
        "markets": ["US", "CN_A"], "adjustments": ["qfq", "hfq", "none"],
        "strategy_families": {
            "baseline": {"baseline_kind": ["naive", "mean", "drift"]},
            "search": {"search_base": ["sm", "fsm"], "search_method": ["bayesian", "genetic", "random"]},
            "regime": {"regime_kind": ["adaptive_router_v1", "dual_state_router", "no_market", "no_router"]},
            "composite": {"composite_policy": ["composite_only", "composite_plus_trend", "composite_plus_reversion", "composite_plus_relative_strength", "composite_plus_macro_cap", "composite_plus_all_advisories"]},
        },
        "default_request": {"family": "regime", "regime_kind": "adaptive_router_v1"},
        "defaults": default_params(), "limits": {"upload_bytes": MAX_UPLOAD_BYTES, "dataset_rows": 10_000, "pending_jobs": MAX_PENDING_JOBS},
        "features": {"research_control": os.getenv("STRATAGY_RESEARCH_CONTROL") == "1", "workspace_ttl_hours": 24},
    }


@app.get(f"{API_PREFIX}/market-context")
def market_context(market: str = 'US', force_refresh: bool = False) -> dict[str, Any]:
    from core.market_context import get_market_context_snapshot
    from .service import json_value
    return json_value(get_market_context_snapshot(normalize_market(market), force_refresh=force_refresh))


@app.get(f"{API_PREFIX}/stocks")
def stocks(market: str = "US", query: str = "", limit: int = Query(20, ge=1, le=100)) -> dict[str, Any]:
    market_key = normalize_market(market)
    if query.strip():
        try:
            matches = search_stock_candidates(query, market_key, limit=limit)
            items = [{"symbol": str(row["symbol"]), "name": str(row.get("name") or ""), "label": str(row.get("label") or row["symbol"]), "market": market_key} for row in matches.to_dict(orient="records")]
        except Exception:
            needle = query.strip().upper()
            items = [{"symbol": symbol, "name": "", "label": symbol, "market": market_key} for symbol in get_available_stocks(market_key) if needle in symbol.upper()][:limit]
    else:
        symbols = get_available_stocks(market_key)[:limit]
        try:
            labels = get_stock_label_map(symbols, market_key)
        except Exception:
            labels = {}
        items = [{"symbol": symbol, "name": labels.get(symbol, ""), "label": labels.get(symbol, symbol), "market": market_key} for symbol in symbols]
    return {"items": items, "count": len(items)}


@app.post(f"{API_PREFIX}/stocks/load")
def load_stock(request: StockLoadRequest) -> dict[str, Any]:
    market = normalize_market(request.market)
    df = load_or_fetch_stock(request.symbol, request.adjust, market=market, force_refresh=request.force_refresh, show_spinner=False)
    try:
        frame = prepare_dataframe(df, start_date=request.start_date, end_date=request.end_date)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    dataset_id = storage.new_id()
    payload = {"symbol": request.symbol.upper() if market == "US" else request.symbol.zfill(6), "market": market, "adjust": request.adjust, "source": "market", "dataframe": frame}
    storage.save_dataset(dataset_id, payload)
    return dataset_summary(dataset_id, payload)


@app.get(f"{API_PREFIX}/datasets/{{dataset_id}}")
def dataset(dataset_id: str) -> dict[str, Any]:
    from .service import records
    payload = _dataset_or_404(dataset_id)
    summary = dataset_summary(dataset_id, payload)
    summary["candles"] = records(payload["dataframe"], ["date", "open", "high", "low", "close", "volume"])
    return summary


@app.post(f"{API_PREFIX}/analysis/portfolio/factors")
def portfolio_factors(request: PortfolioRequest) -> dict[str, Any]:
    from core.visualization import create_factor_score_comparison
    from .service import json_value, validated_params
    datasets = [_dataset_or_404(item) for item in request.dataset_ids]
    try:
        params = validated_params(request.params)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    figure = create_factor_score_comparison({item['symbol']: item['dataframe'] for item in datasets}, **params)
    if figure is None or not figure.data:
        return {'items': [], 'status': 'unavailable'}
    bars = figure.data[0]
    items = [{'symbol': symbol, 'factor_score': score, 'target_position': extra[0], 'percentile': extra[1] / 100}
             for symbol, score, extra in zip(bars.x, bars.y, bars.customdata)]
    missing = sorted(set(item['symbol'] for item in datasets) - set(item['symbol'] for item in items))
    return {'items': json_value(items), 'status': 'partial' if missing else 'available', 'omitted_symbols': missing}


@app.get(f"{API_PREFIX}/datasets/{{dataset_id}}/analysis")
def dataset_presentation(dataset_id: str, period: str = Query('D', pattern='^[DWM]$'),
                         train_ratio: float = Query(.7, ge=.6, le=.9),
                         start_date: str | None = None, end_date: str | None = None) -> dict[str, Any]:
    from .presentation import dataset_analysis
    payload = _dataset_or_404(dataset_id)
    try:
        return dataset_analysis(payload['dataframe'], period=period, train_ratio=train_ratio,
                                start_date=start_date, end_date=end_date)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post(f"{API_PREFIX}/datasets/{{dataset_id}}/slice")
def slice_dataset(dataset_id: str, request: DatasetSliceRequest) -> dict[str, Any]:
    current = _dataset_or_404(dataset_id)
    base = _dataset_or_404(current.get('base_dataset_id') or dataset_id)
    try:
        frame = prepare_dataframe(base['dataframe'], start_date=request.start_date, end_date=request.end_date)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    new_id = storage.new_id()
    payload = {**base, 'dataframe': frame, 'base_dataset_id': current.get('base_dataset_id') or dataset_id}
    storage.save_dataset(new_id, payload)
    return dataset_summary(new_id, payload)


@app.post(f"{API_PREFIX}/datasets/{{dataset_id}}/analysis")
def dataset_presentation_with_params(dataset_id: str, request: DatasetAnalysisRequest) -> dict[str, Any]:
    from .presentation import dataset_analysis
    payload = _dataset_or_404(dataset_id)
    try:
        return dataset_analysis(payload['dataframe'], **request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post(f"{API_PREFIX}/stocks/upload")
async def upload_stock(file: UploadFile = File(...), symbol: str = Form("UPLOAD"), market: str = Form("US"), adjust: str = Form("qfq")) -> dict[str, Any]:
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="CSV upload exceeds 12 MiB")
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(status_code=415, detail="only CSV uploads are supported")
    if not re.fullmatch(r"[A-Za-z0-9.^_-]{1,20}", symbol):
        raise HTTPException(status_code=422, detail="invalid dataset symbol")
    if market not in {"US", "CN_A", "A"} or adjust not in {"qfq", "hfq", "none"}:
        raise HTTPException(status_code=422, detail="invalid market or adjustment")
    try:
        frame = prepare_dataframe(load_uploaded_bytes(content))
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    market_key = normalize_market(market)
    dataset_id = storage.new_id()
    payload = {"symbol": symbol[:20], "market": market_key, "adjust": adjust if adjust in {"qfq", "hfq", "none"} else "qfq", "source": "upload", "filename": file.filename, "dataframe": frame}
    storage.save_dataset(dataset_id, payload)
    return dataset_summary(dataset_id, payload)


@app.post(f"{API_PREFIX}/analysis/single/jobs", status_code=status.HTTP_202_ACCEPTED)
def create_single_job(request: SingleJobRequest) -> dict[str, Any]:
    _dataset_or_404(request.dataset_id)
    with _pending_lock:
        if len(_pending_jobs) >= MAX_PENDING_JOBS:
            raise HTTPException(status_code=429, detail="calculation queue is full")
        job_id = storage.new_id()
        payload = {"job_id": job_id, "runner_id": _runner_id, "status": "queued", "progress": 0.0, "created_at": utc_now(), "started_at": None, "finished_at": None, "error": None, **request.model_dump()}
        storage.save_job(job_id, payload)
        _pending_jobs.add(job_id)
        _executor.submit(_run_job, job_id, payload)
    return {"job_id": job_id, "status": "queued"}


@app.get(f"{API_PREFIX}/analysis/single/jobs/{{job_id}}")
def single_job_status(job_id: str) -> dict[str, Any]:
    job = _job_or_404(job_id)
    return {key: job.get(key) for key in ("job_id", "status", "progress", "created_at", "started_at", "finished_at", "error")}


@app.get(f"{API_PREFIX}/analysis/single/jobs/{{job_id}}/result")
def single_job_result(job_id: str) -> dict[str, Any]:
    job = _job_or_404(job_id)
    if job["status"] != "completed":
        raise HTTPException(status_code=409, detail={"status": job["status"], "error": job.get("error")})
    return job["result"]


@app.get(f"{API_PREFIX}/analysis/single/jobs/{{job_id}}/walk-forward")
def walk_forward(job_id: str, train_window: int = Query(252, ge=20, le=2500), test_window: int = Query(63, ge=5, le=500)) -> dict[str, Any]:
    job = _job_or_404(job_id)
    if job["status"] != "completed":
        raise HTTPException(status_code=409, detail="job is not completed")
    try:
        from .diagnostics import build_walk_forward
        artifact = job["result"]["artifact"]
        value = build_walk_forward(pd.DataFrame(artifact["signals"]), artifact["params"], train_window, test_window)
        from .service import json_value
        return json_value(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ImportError as exc:
        raise HTTPException(status_code=501, detail="walk-forward diagnostics unavailable") from exc


@app.post(f"{API_PREFIX}/analysis/portfolio")
def portfolio(request: PortfolioRequest) -> dict[str, Any]:
    datasets = [{**_dataset_or_404(dataset_id), "dataset_id": dataset_id} for dataset_id in request.dataset_ids]
    try:
        result = run_portfolio_calculation(datasets, request.params, request.weights)
        result_id = storage.new_id()
        result["result_id"] = result_id
        storage.save_job(result_id, {"kind": "portfolio", "status": "completed", "result": result, "created_at": utc_now()})
        return result
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get(f"{API_PREFIX}/analysis/portfolio/results/{{result_id}}")
def portfolio_result(result_id: str) -> dict[str, Any]:
    record = _job_or_404(result_id)
    if record.get("kind") != "portfolio":
        raise HTTPException(status_code=404, detail="portfolio result not found")
    return record["result"]


@app.post(f"{API_PREFIX}/analysis/portfolio/optimize")
def portfolio_optimize(request: PortfolioOptimizeRequest) -> dict[str, Any]:
    datasets = [{**_dataset_or_404(dataset_id), "dataset_id": dataset_id} for dataset_id in request.dataset_ids]
    try:
        return optimize_portfolio(datasets, request.params, request.n_trials)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get(f"{API_PREFIX}/research/catalog")
def catalog(query: str = "") -> dict[str, Any]:
    return research_catalog(query)


@app.get(f"{API_PREFIX}/research/reports/{{experiment_id}}")
def report(experiment_id: str) -> dict[str, Any]:
    value = research_report(experiment_id)
    if value is None:
        raise HTTPException(status_code=404, detail="research report not found")
    return value


@app.get(f"{API_PREFIX}/research/reports/{{experiment_id}}/html", response_class=HTMLResponse)
def report_html(experiment_id: str) -> str:
    value = research_report(experiment_id)
    if value is None:
        raise HTTPException(status_code=404, detail="research report not found")
    return simple_report_html(value["title"], value.get("readme", ""), {"status": value.get("status"), "markets": ", ".join(value.get("markets", []))})


@app.get(f"{API_PREFIX}/reports/final", response_class=HTMLResponse)
def get_final_report(language: str = "zh") -> str:
    try:
        _name, content = final_report(language)
        return content
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get(f"{API_PREFIX}/experiments")
def experiments() -> dict[str, Any]:
    return experiment_snapshots()


def _experiment_control(action: str, campaign_id: str | None = None) -> dict[str, Any]:
    try:
        return control_experiment(action, campaign_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (FileNotFoundError, FileExistsError, RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post(f"{API_PREFIX}/experiments/start")
def start_experiment(request: CampaignStartRequest) -> dict[str, Any]:
    return _experiment_control("start", request.campaign_id)


@app.post(f"{API_PREFIX}/experiments/{{campaign_id}}/pause")
def pause_experiment(campaign_id: str) -> dict[str, Any]:
    return _experiment_control("pause", campaign_id)


@app.post(f"{API_PREFIX}/experiments/{{campaign_id}}/resume")
def resume_experiment(campaign_id: str) -> dict[str, Any]:
    return _experiment_control("resume", campaign_id)


@app.get(f"{API_PREFIX}/exports/single/{{job_id}}.html", response_class=HTMLResponse)
def export_single(job_id: str, language: str = Query("zh", pattern="^(zh|en)$")) -> str:
    job = _job_or_404(job_id)
    if job["status"] != "completed":
        raise HTTPException(status_code=409, detail="job is not completed")
    dataset = _dataset_or_404(job["dataset_id"])
    return single_export_html({**job, "symbol": dataset["symbol"], "market": dataset["market"]}, language)


@app.post(f"{API_PREFIX}/exports/portfolio", response_class=HTMLResponse)
def export_portfolio(request: PortfolioRequest, language: str = Query("zh", pattern="^(zh|en)$")) -> str:
    datasets = [{**_dataset_or_404(dataset_id), "dataset_id": dataset_id} for dataset_id in request.dataset_ids]
    try:
        result = run_portfolio_calculation(datasets, request.params, request.weights)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    from .exporting import build_portfolio_export

    return build_portfolio_export(datasets, result, request.params, language)


FRONTEND_DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"


@app.get("/", include_in_schema=False)
def root_redirect(request: Request) -> RedirectResponse:
    suffix = f"?{request.url.query}" if request.url.query else ""
    return RedirectResponse(f"/strategy/{suffix}")


@app.get("/strategy", include_in_schema=False)
def strategy_redirect(request: Request) -> RedirectResponse:
    suffix = f"?{request.url.query}" if request.url.query else ""
    return RedirectResponse(f"/strategy/{suffix}")


@app.api_route(f"{API_PREFIX}/{{unknown_path:path}}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False)
def unknown_api(unknown_path: str) -> None:
    raise HTTPException(status_code=404, detail="API route not found")


@app.get("/strategy/{full_path:path}", include_in_schema=False)
def spa(full_path: str):
    if not FRONTEND_DIST.is_dir():
        raise HTTPException(status_code=404, detail="frontend build is unavailable")
    candidate = (FRONTEND_DIST / full_path).resolve()
    if FRONTEND_DIST.resolve() in candidate.parents and candidate.is_file():
        return FileResponse(candidate)
    if Path(full_path).suffix:
        raise HTTPException(status_code=404, detail="frontend asset not found")
    return FileResponse(FRONTEND_DIST / "index.html")
