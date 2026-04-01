from __future__ import annotations

import json
import os
from pathlib import Path

import ui.home as home
import ui.model_evaluation as model_evaluation


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

    def container(self, *, key=None):
        self.container_keys.append(key)
        return _FakeBlock(self)

    def columns(self, spec, gap=None):
        count = spec if isinstance(spec, int) else len(spec)
        return [_FakeBlock(self) for _ in range(count)]

    def tabs(self, labels):
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

    def caption(self, text):
        self.captions.append(str(text))

    def dataframe(self, frame, use_container_width=False, hide_index=False):
        _ = use_container_width, hide_index
        self.dataframes.append(frame.copy())

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
    assert payload["feature_labels"]["mlflow"] == "未记录 MLflow"
    assert payload["feature_labels"]["quantstats"] == "未生成"
    assert payload["score_policy_text"] == "仅主窗口总分"
    assert payload["config_name_label"] == "legacy_case"
    assert payload["stock_count_label"] == "N/A"
    assert payload["model_count_label"] == "1"


def test_home_page_contains_model_evaluation_cta(monkeypatch) -> None:
    rendered: list[str] = []

    monkeypatch.setattr(home, "render_route_nav", lambda current: None)
    monkeypatch.setattr(home, "render_html", lambda markup: rendered.append(markup))

    home.render_home_page()

    combined = "\n".join(rendered)
    assert "/strategy/model-evaluation" in combined
    assert "进入模型评估" in combined


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
    assert fake_st.selectbox_calls[0]["label"] == "选择 run"
    assert fake_st.selectbox_calls[0]["options"] == ["demo_run"]
    assert any("Mean" in markup for markup in rendered_html)
    assert any(not frame.empty for frame in fake_st.dataframes)
    assert status_calls
