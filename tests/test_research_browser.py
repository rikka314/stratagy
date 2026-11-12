from __future__ import annotations

import json
from pathlib import Path

import ui.research_browser as research_browser
from ui.research_browser import load_research_experiments, search_research_experiments


def _write_catalog(root: Path) -> Path:
    archive = root / "research" / "00_demo"
    archive.mkdir(parents=True)
    (archive / "README.md").write_text(
        "# Demo\n\n## Frozen scope\n- US, 20 days\n\n## Research flow\n1. Freeze\n\n## Result\nSharpe 0.4\n",
        encoding="utf-8",
    )
    output = root / "model-test" / "outputs" / "demo"
    output.mkdir(parents=True)
    evidence = output / "metrics.csv"
    evidence.write_text("metric,value\nsharpe,0.4\n", encoding="utf-8")
    catalog = root / "research" / "RESEARCH_CATALOG.json"
    catalog.write_text(
        json.dumps(
            {
                "experiments": [
                    {
                        "id": "demo",
                        "title": "Demo research",
                        "archive_path": "research/00_demo",
                        "status": "passed_research_gate",
                        "date_range": "2026-08-01..2026-08-02",
                        "markets": ["US"],
                        "question": "Does it work?",
                        "decision": "Keep it",
                        "gate": "Sharpe",
                        "key_results": {"sharpe": 0.4, "catalog_only_metric": 0.12345},
                        "sources": ["research/00_demo/README.md"],
                        "evidence": [{"path": "model-test/outputs/demo/metrics.csv", "required": True}],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return catalog


def test_archive_reader_is_timeline_sorted_and_traceable(tmp_path: Path) -> None:
    catalog = _write_catalog(tmp_path)
    experiments, issues = load_research_experiments(tmp_path, catalog)
    assert not issues
    assert [item.experiment_id for item in experiments] == ["demo"]
    assert experiments[0].evidence_available == 1
    assert "frozen scope" in experiments[0].sections


def test_archive_search_covers_gate_and_evidence_paths(tmp_path: Path) -> None:
    catalog = _write_catalog(tmp_path)
    experiments, _ = load_research_experiments(tmp_path, catalog)
    assert search_research_experiments(experiments, "Sharpe")
    assert search_research_experiments(experiments, "metrics.csv")
    assert search_research_experiments(experiments, "missing") == []


def test_archive_search_tokenizes_multiword_metric_queries(tmp_path: Path) -> None:
    catalog = _write_catalog(tmp_path)
    experiments, _ = load_research_experiments(tmp_path, catalog)
    assert search_research_experiments(experiments, "Demo Sharpe")
    assert search_research_experiments(experiments, "0.4")
    assert search_research_experiments(experiments, "catalog_only_metric")
    assert search_research_experiments(experiments, "0.12345")


def test_archive_section_keys_are_unique_across_experiments(monkeypatch) -> None:
    class _Block:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class _FakeStreamlit:
        def __init__(self):
            self.keys = []

        def container(self, *, key=None):
            self.keys.append(key)
            return _Block()

        def markdown(self, *_args, **_kwargs):
            return None

    fake = _FakeStreamlit()
    monkeypatch.setattr(research_browser, "st", fake)
    research_browser._render_section("研究计划与范围", "body", fallback="fallback", section_key="first")
    research_browser._render_section("研究计划与范围", "body", fallback="fallback", section_key="second")

    assert len(fake.keys) == 2
    assert len(set(fake.keys)) == 2
    assert all("research-detail-" in key for key in fake.keys)


def test_archive_has_a_chinese_reading_edition(monkeypatch, tmp_path: Path) -> None:
    _ = tmp_path
    experiments, issues = load_research_experiments(research_browser.REPO_ROOT)
    assert not issues
    experiment = next(item for item in experiments if item.experiment_id == "cn_a_composite_only")
    monkeypatch.setattr(research_browser, "get_ui_language_safe", lambda: "zh")

    assert experiment.title == "CN_A Composite-only"
    assert "市场仅为 CN_A" in research_browser._localized_section(experiment, "scope", "frozen scope")
    assert "Composite Sharpe" in research_browser.ZH_METRIC_LABELS[experiment.experiment_id].values()
    assert research_browser.search_research_experiments(experiments, "市场原生")


def test_archive_preserves_catalog_chronology_without_using_dates() -> None:
    experiments, issues = load_research_experiments(research_browser.REPO_ROOT)
    assert not issues
    assert [item.experiment_id for item in experiments] == [
        "baseline_sm_fsm_full_market",
        "transformer_state_feasibility",
        "adaptive_dynamic_experts",
        "cn_a_composite_only",
        "cn_a_composite_advisory",
        "ml_enhancement",
        "us_composite",
        "news_fusion",
        "frontend_evolution",
        "deployment_optimization",
    ]
