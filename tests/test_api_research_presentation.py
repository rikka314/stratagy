from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

import api.research_presentation as presentation


def test_adaptive_chart_preserves_fractional_return_values() -> None:
    frame = pd.DataFrame({
        "split_id": ["fold-1", "fold-2"],
        "candidate_total_return": [0.125, -0.04],
        "adaptive_total_return": [0.10, -0.025],
    })

    title, figure = presentation._figure("adaptive_dynamic_experts", frame, "en")

    assert title.startswith("W11 US")
    assert list(figure.data[0].y) == [0.125, -0.04]
    assert list(figure.data[1].y) == [0.10, -0.025]
    assert figure.layout.yaxis.tickformat == ".1%"


def test_missing_chart_artifact_is_explicitly_unavailable(monkeypatch, tmp_path) -> None:
    experiment = SimpleNamespace(experiment_id="news_fusion", evidence=())
    monkeypatch.setattr(presentation, "_experiments", lambda _root: [experiment])
    monkeypatch.setattr(presentation, "_chart_frame", lambda _experiment, _root: ("", pd.DataFrame()))

    result = presentation.research_chart("news_fusion", tmp_path)

    assert result["available"] is False
    assert result["reason"] == "missing_artifact"
    assert "不是零结果" in result["message"]["zh"]
