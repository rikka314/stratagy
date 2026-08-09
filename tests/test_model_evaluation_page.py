from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import ui.home as home
import ui.model_evaluation as model_evaluation
from core.visualization import create_news_ablation_chart
from ui.export_reports import build_model_evaluation_export_html


class _FakeBlock:
    def __init__(self, host):
        self._host = host

    def __enter__(self):
        return self._host

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeStreamlit:
    def __init__(self) -> None:
        self.selectbox_calls: list[dict[str, object]] = []
        self.markdowns: list[str] = []
        self.captions: list[str] = []
        self.dataframes = []
        self.downloads: list[dict[str, object]] = []
        self.container_keys: list[str | None] = []
        self.divider_count = 0
        self.plotly_figures = []
        self.events: list[tuple[str, object]] = []

    def container(self, *, key=None):
        self.container_keys.append(key)
        return _FakeBlock(self)

    def columns(self, spec, gap=None):
        count = spec if isinstance(spec, int) else len(spec)
        return [_FakeBlock(self) for _ in range(count)]

    def tabs(self, labels):
        self.events.append(("tabs", list(labels)))
        return [_FakeBlock(self) for _ in labels]

    def selectbox(self, label, options, index=0, key=None):
        self.selectbox_calls.append(
            {
                "label": label,
                "options": list(options),
                "index": index,
                "key": key,
            }
        )
        return list(options)[index]

    def markdown(self, text, unsafe_allow_html=False):
        _ = unsafe_allow_html
        self.markdowns.append(text)
        self.events.append(("markdown", text))

    def caption(self, text):
        self.captions.append(str(text))

    def dataframe(self, frame, width=None, hide_index=False):
        _ = width, hide_index
        self.dataframes.append(frame.copy())
        self.events.append(("dataframe", list(frame.columns)))

    def plotly_chart(self, fig, width=None, config=None, key=None):
        _ = width, config, key
        self.plotly_figures.append(fig)
        self.events.append(("plotly_chart", len(fig.data)))

    def download_button(self, label, data, file_name, mime, key=None):
        self.downloads.append(
            {
                "label": label,
                "file_name": file_name,
                "mime": mime,
                "key": key,
                "size": len(data),
            }
        )
        self.events.append(("download", label))

    def divider(self):
        self.divider_count += 1


def test_discover_model_evaluation_runs_filters_and_sorts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    old_run = tmp_path / "good_old"
    new_run = tmp_path / "good_new"
    internal_run = tmp_path / "_internal"
    blocked_run = tmp_path / "blocked"
    read_error_run = tmp_path / "read_error"
    missing_report_run = tmp_path / "missing_report"

    for folder in (old_run, new_run, internal_run, blocked_run, read_error_run, missing_report_run):
        folder.mkdir(parents=True, exist_ok=True)

    (old_run / "report.json").write_text("{}", encoding="utf-8")
    (new_run / "report.json").write_text("{}", encoding="utf-8")
    (internal_run / "report.json").write_text("{}", encoding="utf-8")
    (read_error_run / "report.json").write_text("{}", encoding="utf-8")

    os.utime(old_run / "report.json", (10, 10))
    os.utime(new_run / "report.json", (20, 20))

    original_is_dir = Path.is_dir
    original_is_file = Path.is_file

    def _patched_is_dir(self: Path) -> bool:
        if self.name == "blocked":
            raise PermissionError("blocked")
        return original_is_dir(self)

    def _patched_is_file(self: Path) -> bool:
        if self.name == "report.json" and self.parent.name == "read_error":
            raise OSError("cannot read")
        return original_is_file(self)

    monkeypatch.setattr(Path, "is_dir", _patched_is_dir)
    monkeypatch.setattr(Path, "is_file", _patched_is_file)

    runs = model_evaluation.discover_model_evaluation_runs(tmp_path)

    assert [run.run_id for run in runs] == ["good_new", "good_old"]


def test_normalize_model_evaluation_payload_handles_missing_optional_fields(tmp_path: Path) -> None:
    run_dir = tmp_path / "legacy_case"
    run_dir.mkdir(parents=True, exist_ok=True)
    report_path = run_dir / "report.json"
    report_path.write_text("{}", encoding="utf-8")

    run = model_evaluation.ModelEvaluationRun(
        run_id="legacy_case",
        run_dir=run_dir,
        report_path=report_path,
        modified_ts=0.0,
    )

    payload = model_evaluation.normalize_model_evaluation_payload(
        run,
        {
            "generated_at": "2026-03-29T08:33:52+00:00",
            "config": {"name": "legacy_case", "market": "US"},
            "top_models": [{"display_name": "Mean", "rank": 1}],
        },
        None,
    )

    assert payload["quantstats"] == []
    assert payload["mlflow_recorded"] is False
    assert payload["feature_labels"]["mlflow"] == "Not Logged to MLflow"
    assert payload["feature_labels"]["quantstats"] == "Not Generated"
    assert payload["score_policy_text"] == "Main Window Score Only"
    assert payload["config_name_label"] == "legacy_case"
    assert payload["stock_count_label"] == "N/A"
    assert payload["model_count_label"] == "1"


def _write_research_artifacts(run_dir: Path) -> None:
    (run_dir / "market_strategy_recommendations.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "generated_at": "2026-08-03T08:00:00+00:00",
                "markets": {
                    "US": {
                        "recommendation": "search_mean_v1",
                        "confidence": "high",
                        "evidence": {"winning_rule": "stable in 3 rolling windows"},
                        "limitations": ["Technology stocks are over-represented."],
                    },
                    "CN_A": {
                        "recommendation": None,
                        "confidence": "insufficient_evidence",
                        "evidence": {"decision": "parallel evidence insufficient"},
                        "limitations": ["Smoke universe is too small."],
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    pd.DataFrame(
        [
            {
                "market": "US",
                "strategy_id": "search_mean_v1",
                "strategy_label": "Search Mean",
                "evaluation_window": "main",
                "symbol_count": 20,
                "successful_symbol_count": 19,
                "coverage_rate": 0.95,
                "net_total_return": 0.18,
                "sharpe": 1.35,
                "max_drawdown": -0.11,
                "total_turnover": 3.2,
                "total_transaction_cost": 0.0012,
                "rolling_rank_median": 1.0,
                "rolling_direction_consistency": 0.8,
                "degraded_run_rate": 0.0,
            },
            {
                "market": "CN_A",
                "strategy_id": "naive",
                "strategy_label": "Naive",
                "evaluation_window": "main",
                "symbol_count": 18,
                "successful_symbol_count": 17,
                "coverage_rate": 0.944,
                "net_total_return": 0.04,
                "sharpe": 0.42,
                "max_drawdown": -0.19,
                "total_turnover": 1.0,
                "total_transaction_cost": 0.0008,
                "rolling_rank_median": 2.0,
                "rolling_direction_consistency": 0.5,
                "degraded_run_rate": 0.0,
            },
        ]
    ).to_csv(run_dir / "market_strategy_matrix.csv", index=False)
    pd.DataFrame(
        [
            {
                "market": market,
                "base_strategy_id": "search_mean_v1",
                "news_weight": weight,
                "lookback_days": 3,
                "symbol_count": 20,
                "matched_row_count": 120,
                "coverage_rate": coverage,
                "fallback_position_match_rate": 1.0,
                "future_leakage_violation_count": 0,
                "duplicate_news_row_count": 0,
                "net_total_return": net_return,
                "max_drawdown": -0.12,
                "sharpe": sharpe,
                "status": "ok",
                "skip_reason": "",
            }
            for market, weight, coverage, net_return, sharpe in (
                ("US", 0.0, 0.72, 0.16, 1.22),
                ("US", 0.3, 0.72, 0.18, 1.35),
                ("CN_A", 0.0, 0.41, 0.04, 0.42),
                ("CN_A", 0.3, 0.41, 0.03, 0.34),
            )
        ]
    ).to_csv(run_dir / "news_ablation_summary.csv", index=False)
    (run_dir / "data_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "market": "US",
                "run_id": "cross-market-demo",
                "news": {"coverage_threshold": 0.5},
            }
        ),
        encoding="utf-8",
    )


def test_load_market_research_payload_adapts_frozen_artifacts(tmp_path: Path) -> None:
    run_dir = tmp_path / "cross_market"
    run_dir.mkdir()
    report_path = run_dir / "report.json"
    report_path.write_text("{}", encoding="utf-8")
    _write_research_artifacts(run_dir)
    run = model_evaluation.ModelEvaluationRun("cross_market", run_dir, report_path, 0.0)

    research = model_evaluation.load_market_research_payload(run)

    assert research["available"] is True
    assert research["cross_market_ready"] is True
    assert research["markets"]["US"]["recommendation"] == "search_mean_v1"
    assert len(research["markets"]["US"]["trace_rows"]) == 1
    assert research["markets"]["CN_A"]["confidence"] == "insufficient_evidence"
    assert research["markets"]["CN_A"]["trace_rows"][0]["strategy_id"] == "naive"
    assert len(research["matrix"]) == 2
    assert len(research["news_ablation"]) == 4


def test_normalize_market_research_payload_contains_anomalies(tmp_path: Path) -> None:
    _ = tmp_path
    research = model_evaluation.normalize_market_research_payload(
        recommendations={
            "markets": {
                "US": {
                    "recommendation": "demo",
                    "confidence": "certain",
                    "limitations": "Fixture-only evidence.",
                }
            }
        },
        matrix_records=[{"market": "MARS", "strategy_id": "demo"}],
        news_records=[{"market": "US", "news_weight": 0.0}],
    )

    assert research["cross_market_ready"] is False
    assert research["matrix"] == []
    assert research["markets"]["US"]["confidence"] == "insufficient_evidence"
    assert research["markets"]["CN_A"]["recommendation"] is None
    assert any("unknown confidence" in issue for issue in research["issues"])
    assert any("missing required market 'CN_A'" in issue for issue in research["issues"])
    assert any("unknown market 'MARS'" in issue for issue in research["issues"])


def test_news_ablation_chart_keeps_performance_and_coverage_visible(tmp_path: Path) -> None:
    run_dir = tmp_path / "chart_case"
    run_dir.mkdir()
    (run_dir / "report.json").write_text("{}", encoding="utf-8")
    _write_research_artifacts(run_dir)
    run = model_evaluation.ModelEvaluationRun("chart_case", run_dir, run_dir / "report.json", 0.0)
    research = model_evaluation.load_market_research_payload(run)

    fig = create_news_ablation_chart(research["news_ablation"])

    assert len(fig.data) == 6
    assert fig.layout.yaxis.tickformat == ".1%"
    assert fig.layout.yaxis2.tickformat == ".2f"
    assert fig.layout.yaxis3.tickformat == ".1%"


def test_model_evaluation_export_is_conclusion_first_and_traceable(tmp_path: Path) -> None:
    run_dir = tmp_path / "export_case"
    run_dir.mkdir()
    report_path = run_dir / "report.json"
    report_path.write_text("{}", encoding="utf-8")
    _write_research_artifacts(run_dir)
    run = model_evaluation.ModelEvaluationRun("export_case", run_dir, report_path, 0.0)
    research = model_evaluation.load_market_research_payload(run)
    payload = model_evaluation.normalize_model_evaluation_payload(
        run,
        {"generated_at": "2026-08-03T08:00:00+00:00", "top_models": [], "failures": []},
        research_payload=research,
    )

    export_html = build_model_evaluation_export_html(
        payload=payload,
        news_ablation_fig=create_news_ablation_chart(research["news_ablation"]),
        language="en",
        theme="light",
    )

    assert export_html.index("Conclusion") < export_html.index("Market strategy matrix")
    assert "search_mean_v1" in export_html
    assert "19 successful / 20 total" in export_html
    assert "Naive · 17 successful / 18 total · 1 matrix row(s)" in export_html
    assert "Technology stocks are over-represented." in export_html
    assert "research-news-ablation-chart" in export_html
    assert "market_strategy_matrix.csv" in export_html


def test_home_page_is_reduced_to_the_animated_market_news_stage(monkeypatch) -> None:
    rendered: list[str] = []

    monkeypatch.setattr(home, "render_route_nav", lambda current: None)
    monkeypatch.setattr(home, "render_html", lambda markup, **kwargs: rendered.append(markup))
    monkeypatch.setattr(home, "_news_api_key", lambda: "")
    monkeypatch.setattr(home, "get_home_market_snapshot", home._empty_home_market_snapshot)
    monkeypatch.setattr(home, "_render_stock_controls", lambda snapshot, language: ("US", 0))

    home.render_home_page()

    combined = "\n".join(rendered)
    assert "home-market-stage" in combined
    assert "market-lens" in combined
    assert "market-stock-cloud" in combined
    assert "market-lens-indices" in combined
    assert "market-lens-leaders" in combined
    assert "market-lens-temperature" in combined
    assert "market-pulse-track" not in combined
    assert "market-candle-track" not in combined
    assert "market-platform-title" in combined
    assert "Stock Strategy Analysis Platform" in combined
    assert "market-news-ticker" in combined
    assert "Microsoft" in combined
    assert "hero-shell" not in combined
    assert "support-columns" not in combined


def test_render_model_evaluation_page_minimal_render(tmp_path: Path, monkeypatch) -> None:
    run_dir = tmp_path / "demo_run"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "report.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-03-29T08:33:52+00:00",
                "config": {
                    "name": "demo_run",
                    "market": "US",
                    "run_robustness": False,
                },
                "pool": {"stock_count": 9},
                "top_models": [
                    {
                        "rank": 1,
                        "display_name": "Mean",
                        "family_group": "baseline",
                        "stage": "A",
                        "total_score": 74.0,
                        "median_sharpe": 1.19,
                        "median_excess_return": -0.089,
                    }
                ],
                "model_summary": [
                    {
                        "rank": 1,
                        "display_name": "Mean",
                        "family_group": "baseline",
                        "stage": "A",
                        "total_score": 74.0,
                        "main_total_score": 74.0,
                        "median_sharpe": 1.19,
                        "median_excess_return": -0.089,
                    }
                ],
                "family_summary": [
                    {
                        "family_group": "baseline",
                        "model_count": 1,
                        "avg_total_score": 74.0,
                        "top_display_name": "Mean",
                        "top_total_score": 74.0,
                    }
                ],
                "search_method_summary": [],
                "robustness_summary": [],
                "failures": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    fake_st = _FakeStreamlit()
    rendered_html: list[str] = []
    nav_calls: list[str] = []
    status_calls: list[tuple[str, str]] = []

    monkeypatch.setattr(model_evaluation, "st", fake_st)
    monkeypatch.setattr(model_evaluation, "render_html", lambda markup: rendered_html.append(markup))
    monkeypatch.setattr(model_evaluation, "render_route_nav", lambda current: nav_calls.append(current))
    monkeypatch.setattr(
        model_evaluation,
        "render_status_note",
        lambda message, tone="info": status_calls.append((message, tone)),
    )

    model_evaluation.render_model_evaluation_page(outputs_root=tmp_path)

    assert nav_calls == ["model-evaluation"]
    assert fake_st.selectbox_calls[0]["label"] == "Select run"
    assert fake_st.selectbox_calls[0]["options"] == ["demo_run"]
    assert any("Mean" in markup for markup in rendered_html)
    assert any(not frame.empty for frame in fake_st.dataframes)
    assert status_calls
    assert any("No cross-market recommendation artifact" in message for message, _ in status_calls)


def test_render_model_evaluation_page_shows_conclusion_before_evidence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run_dir = tmp_path / "research_run"
    run_dir.mkdir()
    (run_dir / "report.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-08-03T08:00:00+00:00",
                "config": {"name": "research_run", "market": "US"},
                "pool": {"stock_count": 20},
                "top_models": [{"rank": 1, "display_name": "Search Mean", "total_score": 81.0}],
                "model_summary": [],
                "family_summary": [],
                "search_method_summary": [],
                "robustness_summary": [],
                "failures": [],
            }
        ),
        encoding="utf-8",
    )
    _write_research_artifacts(run_dir)

    fake_st = _FakeStreamlit()
    rendered_html: list[str] = []
    status_calls: list[tuple[str, str]] = []
    monkeypatch.setattr(model_evaluation, "st", fake_st)
    monkeypatch.setattr(model_evaluation, "render_html", lambda markup: rendered_html.append(markup))
    monkeypatch.setattr(model_evaluation, "render_route_nav", lambda current: None)
    monkeypatch.setattr(
        model_evaluation,
        "render_status_note",
        lambda message, tone="info": status_calls.append((message, tone)),
    )

    model_evaluation.render_model_evaluation_page(outputs_root=tmp_path)

    conclusion_event = fake_st.events.index(("markdown", "## US vs CN_A recommendations"))
    first_dataframe_event = next(index for index, event in enumerate(fake_st.events) if event[0] == "dataframe")
    assert conclusion_event < first_dataframe_event
    assert any("search_mean_v1" in markup for markup in rendered_html)
    assert len(fake_st.plotly_figures) == 1
    assert fake_st.downloads[0]["file_name"] == "research_run-research-evidence.html"
    assert any("coverage threshold" in message for message, tone in status_calls if tone == "warning")
    assert any("Recommendation" in frame.columns for frame in fake_st.dataframes)
