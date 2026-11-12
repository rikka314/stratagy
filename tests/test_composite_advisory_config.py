"""Tests for frozen Composite Advisory Phase 0 configuration."""

from pathlib import Path

import pytest

from core.composite_advisory import POLICIES, POLICY_VERSION
from core.composite_advisory_config import load_advisory_config, source_lock


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "model-test/configs/composite_advisory_phase0_1.json"


def test_phase0_config_is_frozen_research_only() -> None:
    config = load_advisory_config(CONFIG)

    assert config["policy_version"] == POLICY_VERSION
    assert tuple(config["policies"]) == POLICIES
    assert config["execution"]["cost_treatment"] == "ohlcv_gross_charge_once"


def test_phase0_source_lock_contains_required_hashes() -> None:
    config = load_advisory_config(CONFIG)
    lock = source_lock(config, CONFIG)

    assert set(lock) == {
        "config_sha256",
        "source_manifest_sha256",
        "macro_data_manifest_sha256",
        "snapshot_artifacts_sha256",
        "macro_artifacts_sha256",
    }
    assert all(len(value) == 64 for value in lock.values())


def test_invalid_config_rejects_non_research_status(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        CONFIG.read_text(encoding="utf-8").replace('"research_only"', '"production"'),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="research_only"):
        load_advisory_config(path)
