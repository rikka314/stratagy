from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from model_test import campaign, execution, runner, universe
from model_test.control import ResearchControl, atomic_write_json
from model_test.models import RunRecord
from model_test.monitoring import build_stage_leaderboards, load_checkpoint_records
from ui.experiment_monitor import research_control_enabled


REPO_ROOT = Path(__file__).resolve().parents[1]


def _record(
    *,
    symbol: str,
    model_id: str,
    stage: str,
    window_id: str = "main",
    window_kind: str = "main",
    sharpe: float = 1.0,
) -> RunRecord:
    return RunRecord(
        symbol=symbol,
        company_name=symbol,
        segment_key="trend__normal",
        trend_bucket="trend",
        volatility_bucket="normal",
        source_kind="test",
        data_path="test.csv",
        window_id=window_id,
        window_kind=window_kind,
        window_start="2020-01-01",
        window_end="2025-01-01",
        window_days=1260,
        stage=stage,
        model_id=model_id,
        display_name=model_id,
        family_group="baseline" if model_id == "naive" else "sm",
        status="success",
        train_annret=0.1,
        test_annret=0.12,
        test_sharpe=sharpe,
        test_maxdd=-0.1,
        test_excess_return=0.02 if model_id != "naive" else 0.0,
        train_test_gap=0.0,
    )


def test_atomic_progress_and_pause_request(tmp_path: Path) -> None:
    control = ResearchControl(tmp_path)
    control.set_phase("stage_a_main", planned_records=10, completed_records=2)
    payload = json.loads((tmp_path / "progress.json").read_text(encoding="utf-8"))
    assert payload["phase"] == "stage_a_main"
    assert payload["planned_records"] == 10
    assert not list(tmp_path.glob("*.tmp"))

    atomic_write_json(tmp_path / "pause.request.json", {"requested_at": "now"})
    assert control.pause_requested() is True


def test_serial_executor_stops_after_checkpointed_batch(monkeypatch) -> None:
    tasks = []
    for index in range(3):
        tasks.append(
            SimpleNamespace(
                data_path=f"data-{index}.csv",
                market="US",
                adjust="qfq",
                symbol=f"S{index}",
                window=SimpleNamespace(
                    window_id="main",
                    kind="main",
                    start_idx=0,
                    end_idx=10,
                    train_ratio=0.7,
                ),
                model=SimpleNamespace(model_id="naive"),
            )
        )
    executed: list[str] = []
    pause = {"requested": False}

    def fake_run_task_batch(batch, _artifacts_root):
        task = batch[0]
        executed.append(task.symbol)
        return [SimpleNamespace(model_id="naive", symbol=task.symbol, window_id="main", status="success")]

    monkeypatch.setattr(execution, "run_task_batch", fake_run_task_batch)

    with pytest.raises(execution.ExecutionPaused):
        execution.execute_tasks(
            tasks,
            1,
            on_record=lambda _record: pause.update(requested=True),
            should_pause=lambda: pause["requested"],
        )
    assert executed == ["S0"]


def test_campaign_create_duplicate_pause_and_resume(tmp_path: Path, monkeypatch) -> None:
    campaigns_root = tmp_path / "outputs" / "_campaigns"
    monkeypatch.setattr(campaign, "CAMPAIGNS_ROOT", campaigns_root)
    monkeypatch.setattr(campaign, "WORKSPACE_ROOT", tmp_path)
    monkeypatch.setattr(campaign, "_git_state", lambda: ("abc123", True))
    monkeypatch.setattr(campaign, "_process_alive", lambda _pid: False)
    monkeypatch.setattr(campaign, "_spawn_worker", lambda _campaign_id: 1234)
    config_paths = [
        REPO_ROOT / "model-test" / "configs" / "smoke_us_deans_gate1.json",
        REPO_ROOT / "model-test" / "configs" / "smoke_cn_a_deans_gate1.json",
    ]

    snapshot = campaign.start_campaign("test-campaign", config_paths=config_paths)
    assert snapshot.campaign["status"] == "preflight"
    with pytest.raises(FileExistsError):
        campaign.start_campaign("test-campaign", config_paths=config_paths)

    state = campaign._load_state("test-campaign")
    state["status"] = "running"
    campaign._write_state("test-campaign", state)
    paused_requested = campaign.request_pause("test-campaign")
    assert paused_requested.pause["requested"] is True

    state = campaign._load_state("test-campaign")
    state["status"] = "paused"
    campaign._write_state("test-campaign", state)
    resumed = campaign.resume_campaign("test-campaign")
    assert resumed.campaign["status"] == "resuming"
    assert resumed.pause["requested"] is False


def test_stale_campaign_pid_becomes_failed(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(campaign, "CAMPAIGNS_ROOT", tmp_path)
    monkeypatch.setattr(campaign, "_process_alive", lambda _pid: False)
    campaign_dir = tmp_path / "stale"
    campaign_dir.mkdir(parents=True)
    atomic_write_json(
        campaign_dir / "campaign.json",
        {
            "schema_version": "1.0",
            "campaign_id": "stale",
            "status": "running",
            "phase": "stage_a_main",
            "runs": [],
            "process": {"manager_pid": 999999, "runner_pid": None},
        },
    )
    snapshot = campaign.load_campaign_snapshot("stale")
    assert snapshot.campaign["status"] == "failed"
    assert snapshot.error and "no longer running" in snapshot.error["message"]


def test_checkpoint_loader_keeps_last_good_snapshot_and_a_share_symbol(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    checkpoint = run_dir / "_checkpoint_runs.csv"
    pd.DataFrame(
        [{"symbol": "000001", "window_id": "main", "window_kind": "main", "model_id": "naive", "stage": "A", "status": "success"}]
    ).to_csv(checkpoint, index=False)
    loaded = load_checkpoint_records(run_dir)
    assert loaded.iloc[0]["symbol"] == "000001"

    checkpoint.write_text('"broken', encoding="utf-8")
    fallback = load_checkpoint_records(run_dir, fallback=loaded)
    assert fallback.iloc[0]["symbol"] == "000001"


def test_stage_leaderboards_are_separate_and_include_coverage() -> None:
    records = pd.DataFrame(
        [
            _record(symbol="AAPL", model_id="naive", stage="A").to_row(),
            _record(symbol="AAPL", model_id="sm", stage="A", sharpe=1.2).to_row(),
            _record(symbol="AAPL", model_id="sm_random_ml_logistic", stage="B", sharpe=1.4).to_row(),
            _record(symbol="AAPL", model_id="sm", stage="A", window_id="rolling_1", window_kind="rolling", sharpe=1.1).to_row(),
        ]
    )
    boards = build_stage_leaderboards(
        records,
        config_path=REPO_ROOT / "model-test" / "configs" / "full_us_deans_60.json",
    )
    assert set(boards["stage_a"]["stage"]) == {"A"}
    assert set(boards["stage_b"]["stage"]) == {"B"}
    assert boards["stage_a"].iloc[0]["coverage"] == pytest.approx(1 / 60)
    assert boards["rolling"].iloc[0]["coverage"] == pytest.approx(1 / 240)


def test_local_control_switch_is_explicit(monkeypatch) -> None:
    monkeypatch.delenv("STRATAGY_RESEARCH_CONTROL", raising=False)
    assert research_control_enabled() is False
    monkeypatch.setenv("STRATAGY_RESEARCH_CONTROL", "1")
    assert research_control_enabled() is True


def test_research_history_cache_does_not_dirty_tracked_sample_data() -> None:
    cache_dir = universe._resolve_data_cache_dir()
    assert cache_dir == (REPO_ROOT / "model-test" / "cache" / "history").resolve()


def test_runner_control_pause_then_resume_to_completion(tmp_path: Path, monkeypatch) -> None:
    source_config = REPO_ROOT / "model-test" / "configs" / "smoke_us_deans_gate1.json"
    config_payload = json.loads(source_config.read_text(encoding="utf-8"))
    config_payload.update(
        {
            "name": "pause_resume_smoke",
            "output_subdir": "pause_resume_smoke",
            "smoke_symbols": ["AAPL"],
            "selected_model_ids": ["naive"],
            "run_stage_b": False,
            "run_robustness": False,
            "parallelism": 1,
            "require_clean_worktree": False,
            "enable_mlflow": False,
            "enable_quantstats": False,
        }
    )
    config_path = tmp_path / "pause_resume_smoke.json"
    config_path.write_text(json.dumps(config_payload), encoding="utf-8")
    workspace_root = tmp_path / "model-test"
    workspace_root.mkdir()
    control_dir = tmp_path / "control"
    control_dir.mkdir()
    monkeypatch.setattr(runner, "WORKSPACE_ROOT", workspace_root)

    atomic_write_json(control_dir / "pause.request.json", {"requested_at": "now"})
    assert runner.main(["--config", str(config_path), "--control-dir", str(control_dir)]) == 75
    (control_dir / "pause.request.json").unlink()

    assert runner.main(["--config", str(config_path), "--control-dir", str(control_dir)]) == 0
    meta = json.loads(
        (workspace_root / "outputs" / "pause_resume_smoke" / "_checkpoint_meta.json").read_text(encoding="utf-8")
    )
    assert meta["phase"] == "completed"
    assert meta["completed_record_count"] == 1
