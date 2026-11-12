from __future__ import annotations

import json
from pathlib import Path

from research.validate_research_catalog import validate_catalog


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_catalog_has_all_evidence_backed_experiment_lines_and_valid_paths() -> None:
    errors, checks = validate_catalog(REPO_ROOT, include_hashes=False)

    assert errors == []
    assert {check.experiment_id for check in checks} == {
        "baseline_sm_fsm_full_market",
        "transformer_state_feasibility",
        "adaptive_dynamic_experts",
        "cn_a_composite_only",
        "cn_a_composite_advisory",
        "news_fusion",
        "frontend_evolution",
        "deployment_optimization",
    }


def test_missing_advisory_outputs_remain_pending_without_fabrication() -> None:
    errors, checks = validate_catalog(REPO_ROOT, include_hashes=False)

    advisory_checks = [
        check for check in checks if check.experiment_id == "cn_a_composite_advisory"
    ]
    assert advisory_checks
    assert all(not check.present for check in advisory_checks)
    assert all(not (REPO_ROOT / check.path).exists() for check in advisory_checks)
    assert not any("cn_a_composite_advisory" in error for error in errors)


def test_passed_experiment_requires_present_required_evidence(tmp_path: Path) -> None:
    catalog = {
        "experiments": [
            {
                "id": "fixture",
                "title": "Fixture",
                "archive_path": "archive",
                "status": "passed_research_gate",
                "date_range": "2026-01-01",
                "markets": ["CN_A"],
                "question": "Question",
                "decision": "Decision",
                "gate": "Gate",
                "sources": [],
                "evidence": [{"path": "outputs/manifest.json", "required": True}],
            }
        ]
    }
    (tmp_path / "research").mkdir()
    (tmp_path / "archive").mkdir()
    (tmp_path / "research" / "RESEARCH_CATALOG.json").write_text(
        json.dumps(catalog), encoding="utf-8"
    )

    errors, _checks = validate_catalog(tmp_path, include_hashes=False)

    assert any("passed experiment requires missing evidence" in error for error in errors)


def test_validator_does_not_modify_catalog_or_create_evidence(tmp_path: Path) -> None:
    catalog = {
        "experiments": [
            {
                "id": "pending_fixture",
                "title": "Pending",
                "archive_path": "archive",
                "status": "pending",
                "date_range": "2026-01-01",
                "markets": ["US"],
                "question": "Question",
                "decision": "Decision",
                "gate": "Gate",
                "sources": [],
                "evidence": [{"path": "outputs/missing.json", "required": True}],
            }
        ]
    }
    (tmp_path / "research").mkdir()
    (tmp_path / "archive").mkdir()
    catalog_path = tmp_path / "research" / "RESEARCH_CATALOG.json"
    original = json.dumps(catalog)
    catalog_path.write_text(original, encoding="utf-8")

    errors, checks = validate_catalog(tmp_path, include_hashes=False)

    assert errors == []
    assert len(checks) == 1
    assert checks[0].present is False
    assert catalog_path.read_text(encoding="utf-8") == original
    assert not (tmp_path / "outputs" / "missing.json").exists()
