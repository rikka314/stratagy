from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from html import escape
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
ASSET_ROOT = ROOT / "reports" / "strategy-story-assets"
CHART_DIR = ASSET_ROOT / "charts"
POSTER_DIR = ASSET_ROOT / "posters"

PAPER = "#fffefa"
PAPER_2 = "#f4f1e9"
INK = "#171713"
INK_2 = "#4f4d46"
INK_3 = "#767168"
LINE = "#d8d2c5"
VIOLET = "#6f58e8"
VIOLET_2 = "#9f8cff"
CYAN = "#2c918e"
CORAL = "#e86f56"
LIME = "#d8e886"
MINT = "#bce6cf"

FONT_SANS = "Inter,Segoe UI,PingFang SC,Microsoft YaHei,sans-serif"
FONT_SERIF = "Iowan Old Style,Baskerville,Songti SC,STSong,serif"
FONT_MONO = "SFMono-Regular,Consolas,Liberation Mono,monospace"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source(path: Path) -> dict[str, Any]:
    relative = path.relative_to(ROOT).as_posix()
    if not path.exists():
        return {"path": relative, "available": False, "sha256": None, "bytes": 0}
    return {
        "path": relative,
        "available": True,
        "sha256": _sha256(path),
        "bytes": path.stat().st_size,
    }


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _num(value: Any) -> float:
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError("missing numeric value")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid numeric value: {value!r}") from exc


def _svg_text(
    x: float,
    y: float,
    text: Any,
    *,
    size: int = 24,
    fill: str = INK,
    weight: int = 500,
    anchor: str = "start",
    family: str = FONT_SANS,
    letter_spacing: float | None = None,
) -> str:
    spacing = "" if letter_spacing is None else f' letter-spacing="{letter_spacing}"'
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" fill="{fill}" font-family="{escape(family)}" '
        f'font-size="{size}" font-weight="{weight}" text-anchor="{anchor}"{spacing}>'
        f"{escape(str(text))}</text>"
    )


def _badge(x: float, y: float, label: str, *, fill: str = PAPER_2, color: str = INK_2) -> str:
    width = max(108, len(label) * 9 + 28)
    return (
        f'<rect x="{x}" y="{y}" width="{width}" height="32" rx="16" fill="{fill}"/>'
        + _svg_text(x + width / 2, y + 22, label, size=13, fill=color, weight=700, anchor="middle", family=FONT_MONO)
    )


def _chart_shell(
    title: str,
    subtitle: str,
    body: str,
    *,
    height: int = 720,
    badges: Iterable[tuple[str, str, str]] = (),
    footer: str = "",
) -> str:
    badge_markup: list[str] = []
    badge_x = 56.0
    for label, fill, color in badges:
        badge_markup.append(_badge(badge_x, 112, label, fill=fill, color=color))
        badge_x += max(108, len(label) * 9 + 28) + 10
    footer_markup = _svg_text(56, height - 28, footer, size=14, fill=INK_3, family=FONT_MONO) if footer else ""
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 {height}" role="img" aria-label="{escape(title)}">
  <rect width="1200" height="{height}" rx="28" fill="{PAPER}"/>
  <rect x="1" y="1" width="1198" height="{height - 2}" rx="27" fill="none" stroke="{LINE}"/>
  {_svg_text(56, 62, title, size=38, weight=650, family=FONT_SERIF)}
  {_svg_text(56, 94, subtitle, size=17, fill=INK_2)}
  {''.join(badge_markup)}
  {body}
  {footer_markup}
</svg>
'''


def _unavailable_chart(
    title: str,
    sources: list[dict[str, Any]],
    reason: str = "缺少冻结源文件，未生成替代数据",
) -> str:
    missing = [item["path"] for item in sources if not item["available"]]
    source_labels = missing or [item["path"] for item in sources]
    body = (
        '<rect x="56" y="176" width="1088" height="420" rx="24" fill="#f8f4ea" stroke="#d8d2c5"/>'
        + _svg_text(600, 330, "UNAVAILABLE", size=48, fill=CORAL, weight=750, anchor="middle", family=FONT_MONO)
        + _svg_text(600, 380, reason, size=24, fill=INK_2, anchor="middle")
        + _svg_text(600, 425, "；".join(source_labels)[:100], size=14, fill=INK_3, anchor="middle", family=FONT_MONO)
    )
    return _chart_shell(title, "Source validation failed", body, badges=[("UNAVAILABLE", "#f8d8d0", CORAL)])


def _chart_01() -> tuple[str, str, dict[str, Any]]:
    us_path = ROOT / "model-test" / "outputs" / "full_us_deans_60" / "model_summary.csv"
    cn_path = ROOT / "model-test" / "outputs" / "full_cn_a_deans_60" / "model_summary.csv"
    sources = [_source(us_path), _source(cn_path)]
    if not all(item["available"] for item in sources):
        svg = _unavailable_chart("复杂度没有自动换来更强", sources)
        return "01_model_leaderboard.svg", svg, _manifest_item("01", "unavailable", "US / CN_A", sources)

    us_rows = sorted(_read_csv(us_path), key=lambda row: _num(row.get("total_score")), reverse=True)[:6]
    cn_rows = sorted(_read_csv(cn_path), key=lambda row: _num(row.get("total_score")), reverse=True)[:6]
    if not us_rows or not cn_rows:
        raise ValueError("empty model leaderboard")
    if not any(row.get("model_id") == "sm_bayesian" for row in us_rows):
        raise ValueError("US highlighted model is absent from the displayed ranking")
    if not any(row.get("model_id") == "sm" for row in cn_rows):
        raise ValueError("CN_A highlighted model is absent from the displayed ranking")
    body: list[str] = []
    for panel_x, title, rows, highlight in [
        (56, "US · 60 symbols", us_rows, "sm_bayesian"),
        (626, "CN_A · 60 symbols", cn_rows, "sm"),
    ]:
        body.append(_svg_text(panel_x, 186, title, size=20, weight=700, family=FONT_MONO))
        body.append(f'<line x1="{panel_x}" y1="202" x2="{panel_x + 518}" y2="202" stroke="{LINE}"/>')
        for index, row in enumerate(rows):
            y = 232 + index * 66
            score = _num(row.get("total_score"))
            is_highlight = row.get("model_id") == highlight
            color = VIOLET if is_highlight else CYAN if str(row.get("family_group")) == "sm" else "#aaa397"
            body.append(_svg_text(panel_x, y + 17, row.get("display_name") or row.get("model_id"), size=16, weight=700 if is_highlight else 550))
            body.append(f'<rect x="{panel_x}" y="{y + 28}" width="410" height="12" rx="6" fill="#e9e3d7"/>')
            body.append(f'<rect x="{panel_x}" y="{y + 28}" width="{score * 4.1:.1f}" height="12" rx="6" fill="{color}"/>')
            body.append(_svg_text(panel_x + 500, y + 39, f"{score:.2f}", size=16, weight=750, anchor="end", family=FONT_MONO, fill=color))
    body.append(_svg_text(56, 652, "排名反映同一市场内的综合研究分，不是收益率或未来表现。", size=17, fill=INK_2))
    svg = _chart_shell(
        "复杂度没有自动换来更强",
        "同一研究协议下，更复杂的 ML / FSM 分支没有稳定占据第一。",
        "".join(body),
        badges=[("BASELINE FROZEN", LIME, INK), ("MARKET-LOCAL", MINT, INK)],
        footer="Source: full_us_deans_60/model_summary.csv · full_cn_a_deans_60/model_summary.csv",
    )
    return "01_model_leaderboard.svg", svg, _manifest_item("01", "baseline_frozen", "US / CN_A", sources)


def _chart_02() -> tuple[str, str, dict[str, Any]]:
    catalog_path = ROOT / "research" / "RESEARCH_CATALOG.json"
    sources = [_source(catalog_path)]
    if not sources[0]["available"]:
        svg = _unavailable_chart("相似度提高，决策效用反而下降", sources)
        return "02_transformer_stop.svg", svg, _manifest_item("02", "unavailable", "US", sources)
    catalog = _read_json(catalog_path)
    record = next(item for item in catalog.get("experiments", []) if item.get("id") == "transformer_state_feasibility")
    values = record["key_results"]
    groups = [
        ("B01 · single-day PCA", _num(values["v3_b01_utility_consistency_delta_vs_random"]), _num(values["v3_b01_query_selected_utility_delta_vs_random"])),
        ("B02 · 20-day summary", _num(values["v3_b02_utility_consistency_delta_vs_random"]), _num(values["v3_b02_query_selected_utility_delta_vs_random"])),
    ]
    body: list[str] = [f'<line x1="600" y1="204" x2="600" y2="500" stroke="{INK_3}" stroke-width="1.5"/>']
    scale = 13000
    for index, (label, consistency, utility) in enumerate(groups):
        y = 250 + index * 132
        body.append(_svg_text(56, y - 26, label, size=18, weight=700, family=FONT_MONO))
        body.append(_svg_text(570, y + 5, "一致性", size=15, fill=CYAN, anchor="end"))
        body.append(f'<rect x="600" y="{y - 17}" width="{consistency * scale:.1f}" height="26" rx="7" fill="{CYAN}"/>')
        body.append(_svg_text(610 + consistency * scale, y + 3, f"+{consistency:.6f}", size=15, fill=CYAN, family=FONT_MONO))
        body.append(_svg_text(570, y + 52, "决策效用", size=15, fill=CORAL, anchor="end"))
        utility_width = abs(utility) * scale
        body.append(f'<rect x="{600 - utility_width:.1f}" y="{y + 30}" width="{utility_width:.1f}" height="26" rx="7" fill="{CORAL}"/>')
        body.append(_svg_text(590 - utility_width, y + 50, f"{utility:.6f}", size=15, fill=CORAL, family=FONT_MONO, anchor="end"))
    body.append(f'<rect x="56" y="530" width="1088" height="100" rx="18" fill="#f8e1db"/>')
    body.append(_svg_text(86, 573, "STOP", size=30, fill=CORAL, weight=800, family=FONT_MONO))
    body.append(_svg_text(210, 569, "表示方法能找到“相似”，但这些相似状态没有选出更好的专家。", size=20, fill=INK))
    body.append(_svg_text(210, 602, "因此在 Transformer 训练前停止，而不是调整门槛制造成功。", size=17, fill=INK_2))
    svg = _chart_shell(
        "相似度提高，决策效用反而下降",
        "工程链通过不等于研究假设成立。",
        "".join(body),
        badges=[("STOPPED", "#f8d8d0", CORAL), ("US", MINT, INK), ("SAMPLE UNAVAILABLE", PAPER_2, INK_2)],
        footer="Source: research/RESEARCH_CATALOG.json · transformer_state_feasibility",
    )
    return "02_transformer_stop.svg", svg, _manifest_item("02", "stopped", "US", sources)


def _chart_03() -> tuple[str, str, dict[str, Any]]:
    path = ROOT / "model-test" / "outputs" / "phase2_weight_optimization" / "optimization_results.json"
    sources = [_source(path)]
    if not sources[0]["available"]:
        svg = _unavailable_chart("从“全都要”到五因子", sources)
        return "03_factor_selection.svg", svg, _manifest_item("03", "unavailable", "US", sources)
    payload = _read_json(path)["feature_selection"]
    selected = set(payload["selected_factors"])
    rows = sorted(payload["importance"].items(), key=lambda item: item[1], reverse=True)
    if len(selected) != 5 or len(rows) != 7:
        raise ValueError("factor selection no longer contains five of seven candidates")
    max_importance = max(_num(importance) for _, importance in rows)
    labels = {
        "mom_short_z": "短周期动量",
        "rsi_z": "RSI",
        "macd_z": "MACD",
        "vix_level": "VIX 水平",
        "volume_ratio_rank": "成交量比率",
        "bb_position_rank": "布林带位置",
        "vix_regime": "VIX 状态",
    }
    body: list[str] = []
    for index, (name, importance) in enumerate(rows):
        y = 198 + index * 58
        active = name in selected
        color = VIOLET if active else "#c6bfb2"
        body.append(_svg_text(56, y + 16, labels.get(name, name), size=17, weight=700 if active else 500))
        body.append(_svg_text(226, y + 16, name, size=13, fill=INK_3, family=FONT_MONO))
        body.append(f'<rect x="470" y="{y}" width="520" height="20" rx="10" fill="#e9e3d7"/>')
        body.append(f'<rect x="470" y="{y}" width="{_num(importance) / max_importance * 520:.1f}" height="20" rx="10" fill="{color}"/>')
        body.append(_svg_text(1020, y + 16, importance, size=15, fill=color, weight=750, family=FONT_MONO))
        body.append(_badge(1062, y - 7, "保留" if active else "剔除", fill=MINT if active else PAPER_2, color=CYAN if active else INK_3))
    body.append(_svg_text(56, 638, "筛选后的五个因子：动量、RSI、MACD、VIX、成交量比率。", size=19, fill=INK_2))
    svg = _chart_shell(
        "从“全都要”到五因子",
        "不是继续堆因子，而是用重要性与冗余检查做减法。",
        "".join(body),
        badges=[("5 / 7 SELECTED", LIME, INK), ("US", MINT, INK), ("SAMPLE UNAVAILABLE", PAPER_2, INK_2)],
        footer="Source: phase2_weight_optimization/optimization_results.json",
    )
    return "03_factor_selection.svg", svg, _manifest_item("03", "research_only", "US", sources)


def _chart_04() -> tuple[str, str, dict[str, Any]]:
    phase2_path = ROOT / "model-test" / "outputs" / "phase2_weight_optimization" / "optimization_results.json"
    advanced_path = ROOT / "model-test" / "outputs" / "phase2_5_advanced_optimization" / "advanced_optimization_results.json"
    sources = [_source(phase2_path), _source(advanced_path)]
    if not all(item["available"] for item in sources):
        svg = _unavailable_chart("允许负权重后的优化跃迁", sources)
        return "04_optimization_ladder.svg", svg, _manifest_item("04", "unavailable", "US", sources)
    phase2 = _read_json(phase2_path)
    advanced = _read_json(advanced_path)
    stages = [
        ("正权重 Grid", _num(phase2["grid_search"]["best_score"])),
        ("扩展 Grid", _num(advanced["expanded_grid_search"]["best_score"])),
        ("Bayesian", _num(advanced["bayesian_opt"]["best_score"])),
        ("+ 交互项", _num(advanced["interaction_test"]["best_interaction"]["score"])),
    ]
    body: list[str] = []
    points: list[tuple[float, float]] = []
    for index, (label, score) in enumerate(stages):
        x = 108 + index * 294
        y = 302 - score * 112
        points.append((x, y))
        body.append(f'<circle cx="{x}" cy="{y:.1f}" r="12" fill="{VIOLET if index else CYAN}"/>')
        body.append(_svg_text(x, y - 24, f"{score:.4f}", size=22, fill=VIOLET if index else CYAN, weight=800, anchor="middle", family=FONT_MONO))
        body.append(_svg_text(x, 332, label, size=15, fill=INK_2, weight=650, anchor="middle"))
    body.insert(0, f'<polyline points="{" ".join(f"{x},{y:.1f}" for x, y in points)}" fill="none" stroke="{VIOLET_2}" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>')
    body.append(f'<line x1="56" y1="370" x2="1144" y2="370" stroke="{LINE}"/>')

    weights = dict(advanced["bayesian_opt"]["best_weights"])
    interaction = advanced["interaction_test"]["best_interaction"]
    weights["volume × momentum"] = _num(interaction["best_weight"])
    label_map = {
        "mom_short_z": "短周期动量",
        "rsi_z": "RSI",
        "macd_z": "MACD",
        "vix_level": "VIX 水平",
        "volume_ratio_rank": "成交量比率",
        "volume × momentum": "成交量 × 动量",
    }
    center = 650
    scale = 170
    for index, (name, weight) in enumerate(weights.items()):
        y = 414 + index * 43
        width = abs(_num(weight)) / 2.0 * scale
        x = center if _num(weight) >= 0 else center - width
        color = CYAN if _num(weight) >= 0 else CORAL
        body.append(_svg_text(56, y + 16, label_map.get(name, name), size=16, weight=650))
        body.append(f'<rect x="{x:.1f}" y="{y}" width="{width:.1f}" height="20" rx="8" fill="{color}"/>')
        body.append(_svg_text(center + (width + 14 if _num(weight) >= 0 else -width - 14), y + 16, f"{_num(weight):+.2f}", size=15, fill=color, weight=750, family=FONT_MONO, anchor="start" if _num(weight) >= 0 else "end"))
    body.append(f'<line x1="{center}" y1="398" x2="{center}" y2="676" stroke="{INK_3}"/>')
    svg = _chart_shell(
        "允许负权重后的优化跃迁",
        "负权重、连续优化和交互项，让模型从单因子依赖转向平衡组合。",
        "".join(body),
        height=760,
        badges=[
            (f"{stages[0][1]:.4f} → {stages[-1][1]:.4f}", LIME, INK),
            ("US DIAGNOSTIC", PAPER_2, INK_2),
            ("SAMPLE UNAVAILABLE", PAPER_2, INK_2),
        ],
        footer="Source: phase2_weight_optimization + phase2_5_advanced_optimization",
    )
    return "04_optimization_ladder.svg", svg, _manifest_item("04", "research_diagnostic", "US", sources)


def _chart_05() -> tuple[str, str, dict[str, Any]]:
    path = ROOT / "model-test" / "outputs" / "cn_a_factor_composite_comparison" / "comparison_metrics.csv"
    sources = [_source(path)]
    if not sources[0]["available"]:
        svg = _unavailable_chart("Composite 与 SM / FSM 的冻结比较", sources)
        return "05_cn_a_comparison.svg", svg, _manifest_item("05", "unavailable", "CN_A", sources)
    rows = _read_csv(path)
    if {row.get("model_name") for row in rows} != {"composite_only", "sm", "fsm"}:
        raise ValueError("CN_A comparison model set is incomplete")
    name_map = {"composite_only": "Composite", "sm": "SM", "fsm": "FSM"}
    colors = {"composite_only": VIOLET, "sm": CYAN, "fsm": "#a99f91"}
    body: list[str] = []
    body.append(_svg_text(56, 190, "Sharpe 均值", size=21, weight=750, family=FONT_MONO))
    body.append(_svg_text(632, 190, "最大回撤均值", size=21, weight=750, family=FONT_MONO))
    for index, row in enumerate(rows):
        y = 234 + index * 104
        model = row["model_name"]
        sharpe = _num(row["sharpe_mean"])
        drawdown = _num(row["drawdown_mean"])
        color = colors.get(model, INK_3)
        body.append(_svg_text(56, y + 20, name_map.get(model, model), size=18, weight=750))
        body.append(f'<rect x="170" y="{y}" width="360" height="28" rx="10" fill="#e9e3d7"/>')
        body.append(f'<rect x="170" y="{y}" width="{sharpe / 0.65 * 360:.1f}" height="28" rx="10" fill="{color}"/>')
        body.append(_svg_text(550, y + 21, f"{sharpe:.4f}", size=17, fill=color, weight=750, anchor="end", family=FONT_MONO))
        body.append(_svg_text(632, y + 20, name_map.get(model, model), size=18, weight=750))
        body.append(f'<rect x="746" y="{y}" width="320" height="28" rx="10" fill="#e9e3d7"/>')
        body.append(f'<rect x="746" y="{y}" width="{abs(drawdown) / 0.8 * 320:.1f}" height="28" rx="10" fill="{CORAL if model == "composite_only" else "#c99487"}"/>')
        body.append(_svg_text(1100, y + 21, f"{drawdown:.2%}", size=17, fill=CORAL, weight=750, anchor="end", family=FONT_MONO))
        body.append(_svg_text(170, y + 58, f"records: {row.get('n_folds', 'N/A')}", size=13, fill=INK_3, family=FONT_MONO))
    body.append(f'<rect x="56" y="558" width="1088" height="78" rx="18" fill="#f3eee4"/>')
    body.append(_svg_text(82, 590, "读取边界", size=16, fill=INK, weight=750, family=FONT_MONO))
    body.append(_svg_text(82, 616, "只比较 Sharpe 与回撤；不采用覆盖不完全配对的平均收益，也不把默认 turnover=0 当作证据。", size=16, fill=INK_2))
    svg = _chart_shell(
        "Composite 与 SM / FSM 的冻结比较",
        "CN_A · 同一研究协议下，Composite 排名领先，但回撤仍然很大。",
        "".join(body),
        badges=[("PASSED RESEARCH GATE", LIME, INK), ("CN_A ONLY", MINT, INK)],
        footer="Source: cn_a_factor_composite_comparison/comparison_metrics.csv",
    )
    return "05_cn_a_comparison.svg", svg, _manifest_item("05", "passed_research_gate", "CN_A", sources)


def _chart_06() -> tuple[str, str, dict[str, Any]]:
    csv_path = ROOT / "model-test" / "outputs" / "composite_vs_sm_comparison" / "comparison_metrics.csv"
    readme_path = ROOT / "model-test" / "outputs" / "composite_vs_sm_comparison" / "README.md"
    sources = [_source(csv_path), _source(readme_path)]
    if not all(item["available"] for item in sources):
        svg = _unavailable_chart("为什么需要 Advisor：持仓饱和诊断", sources)
        return "06_saturation_diagnostic.svg", svg, _manifest_item("06", "unavailable", "US", sources)
    rows = [row for row in _read_csv(csv_path) if row.get("model") == "composite_optimized"]
    if len(rows) != 5:
        raise ValueError("saturation diagnostic requires five frozen US samples")
    body: list[str] = []
    for index, row in enumerate(rows):
        x = 60 + index * 218
        exposure = _num(row.get("near_full_exposure"))
        drawdown = _num(row.get("max_drawdown"))
        body.append(_svg_text(x + 92, 224, row.get("symbol", "N/A"), size=22, weight=800, anchor="middle", family=FONT_MONO))
        body.append(f'<rect x="{x}" y="250" width="184" height="230" rx="20" fill="#eee8dc"/>')
        fill_height = exposure * 230
        body.append(f'<rect x="{x}" y="{480 - fill_height:.1f}" width="184" height="{fill_height:.1f}" rx="20" fill="{VIOLET}" opacity=".88"/>')
        body.append(_svg_text(x + 92, 372, f"{exposure:.0%}", size=34, fill=PAPER, weight=850, anchor="middle", family=FONT_MONO))
        body.append(_svg_text(x + 92, 516, "接近满仓", size=14, fill=INK_3, anchor="middle"))
        body.append(_svg_text(x + 92, 548, f"回撤 {drawdown:.1%}", size=16, fill=CORAL, weight=750, anchor="middle", family=FONT_MONO))
    body.append(f'<rect x="56" y="584" width="1088" height="74" rx="18" fill="#f8e1db"/>')
    body.append(_svg_text(82, 614, "DIAGNOSTIC ONLY", size=16, fill=CORAL, weight=800, family=FONT_MONO))
    body.append(_svg_text(266, 614, "Phase 3 manifest 为 data_quality_blocked；这张图只解释问题来源，不证明改进已经准入。", size=16, fill=INK_2))
    body.append(_svg_text(82, 642, "各样例的 near-full exposure 按源表逐项显示，用于量化定位“拿住不松”。", size=15, fill=INK_2))
    svg = _chart_shell(
        "为什么需要 Advisor：持仓饱和诊断",
        "US · 五只样例中的 Composite 几乎始终保持满仓暴露。",
        "".join(body),
        badges=[("DIAGNOSTIC ONLY", "#f8d8d0", CORAL), ("DATA QUALITY BLOCKED", PAPER_2, INK_2)],
        footer="Source: composite_vs_sm_comparison/comparison_metrics.csv + README.md",
    )
    return "06_saturation_diagnostic.svg", svg, _manifest_item("06", "diagnostic_only", "US", sources)


def _chart_07() -> tuple[str, str, dict[str, Any]]:
    early_path = ROOT / "model-test" / "outputs" / "composite_advisory_phase1" / "admission_summary.json"
    early_metrics_path = ROOT / "model-test" / "outputs" / "composite_advisory_phase1" / "ablation_metrics.csv"
    strict_summary_path = ROOT / "model-test" / "outputs" / "composite_stability_phase4_advisory" / "admission_summary.csv"
    fold_path = ROOT / "model-test" / "outputs" / "composite_stability_phase4_advisory" / "fold_metrics.csv"
    sources = [_source(early_path), _source(early_metrics_path), _source(strict_summary_path), _source(fold_path)]
    if not all(item["available"] for item in sources):
        svg = _unavailable_chart("“解决了”之后，还要再验证", sources)
        return "07_advisory_gate.svg", svg, _manifest_item("07", "unavailable", "US", sources)
    early = _read_json(early_path)
    early_metrics = _read_csv(early_metrics_path)
    strict = _read_csv(strict_summary_path)
    folds = _read_csv(fold_path)
    early_reversion = early["policies"]["composite_plus_reversion"]
    if (
        early["status"] != "admitted"
        or "composite_plus_reversion" not in early["admitted_policies"]
        or len(early_reversion["cross_fold"]) != 3
        or not all(fold["passed"] for fold in early_reversion["cross_fold"])
    ):
        raise ValueError("early advisory admission no longer matches the frozen story")
    strict_lookup = {row["strategy_variant"]: row for row in strict}
    by_fold_policy = {(row["fold_id"], row["strategy_variant"]): row for row in folds}
    policies = [
        ("cash", "Cash"),
        ("composite_only", "Composite"),
        ("composite_plus_trend", "Trend"),
        ("composite_plus_reversion", "Reversion"),
        ("composite_plus_macro_cap", "Macro cap"),
        ("composite_plus_relative_strength", "Relative"),
        ("composite_plus_all_advisories", "All"),
    ]
    expected_policies = {policy for policy, _ in policies}
    if set(strict_lookup) != expected_policies:
        raise ValueError("strict advisory summary no longer contains the seven frozen policies")
    if any(int(_num(strict_lookup[policy]["total_folds"])) != 4 for policy in expected_policies):
        raise ValueError("strict advisory denominator is no longer four folds")
    if any(int(_num(strict_lookup[policy]["folds_passed"])) != 0 for policy in expected_policies):
        raise ValueError("strict advisory result is no longer zero of four for every displayed policy")
    reversion_metrics = [row for row in early_metrics if row.get("policy") == "composite_plus_reversion"]
    if len(reversion_metrics) != 3:
        raise ValueError("early reversion metrics no longer contain three folds")
    early_fallback_rate = max(_num(row["fallback_rate"]) for row in reversion_metrics)
    fold_ids = ["fold_01", "fold_02", "fold_03", "fold_04"]
    body: list[str] = []
    body.append(f'<rect x="56" y="180" width="320" height="430" rx="22" fill="#eef2d4"/>')
    body.append(_svg_text(82, 220, "EARLY · 3 FOLDS", size=15, fill=INK_2, weight=800, family=FONT_MONO))
    body.append(_svg_text(82, 272, "Reversion", size=34, fill=VIOLET, weight=750, family=FONT_SERIF))
    body.append(_svg_text(82, 314, "ADMITTED", size=25, fill=CYAN, weight=850, family=FONT_MONO))
    body.append(_svg_text(82, 356, "三折增量 gate 全部通过", size=17, fill=INK))
    body.append(_svg_text(82, 386, "风险改善：是", size=16, fill=INK_2))
    body.append(_svg_text(82, 416, f"fallback 上限：{early_fallback_rate:.0%}", size=16, fill=INK_2))
    body.append(_svg_text(82, 478, "当时我认为", size=15, fill=INK_3))
    body.append(_svg_text(82, 512, "“Advisor 解决了问题。”", size=22, fill=INK, weight=700))
    body.append(_svg_text(82, 570, f"status: {early['status']}", size=13, fill=INK_3, family=FONT_MONO))

    start_x = 470
    body.append(_svg_text(start_x, 190, "STRICT · 4 FOLDS · Sharpe Δ / DD improvement", size=16, fill=INK_2, weight=800, family=FONT_MONO))
    for col, fold_id in enumerate(fold_ids):
        body.append(_svg_text(start_x + 172 + col * 145, 230, fold_id.replace("fold_0", "F"), size=15, fill=INK_3, weight=700, anchor="middle", family=FONT_MONO))
    for row_index, (policy, label) in enumerate(policies):
        y = 254 + row_index * 68
        body.append(_svg_text(start_x, y + 33, label, size=15, weight=700, family=FONT_MONO))
        for col, fold_id in enumerate(fold_ids):
            x = start_x + 104 + col * 145
            current = by_fold_policy.get((fold_id, policy), {})
            baseline = by_fold_policy.get((fold_id, "composite_only"), {})
            sharpe_delta = _num(current.get("sharpe_ratio")) - _num(baseline.get("sharpe_ratio"))
            dd_improvement = (abs(_num(baseline.get("max_drawdown"))) - abs(_num(current.get("max_drawdown")))) * 100
            if sharpe_delta >= 0 and dd_improvement >= 0:
                fill = MINT
            elif sharpe_delta < 0 and dd_improvement < 0:
                fill = "#f3c9bf"
            else:
                fill = "#e5ddf8"
            body.append(f'<rect x="{x}" y="{y}" width="132" height="54" rx="12" fill="{fill}"/>')
            body.append(_svg_text(x + 66, y + 21, f"ΔS {sharpe_delta:+.3f}", size=13, fill=INK, weight=750, anchor="middle", family=FONT_MONO))
            body.append(_svg_text(x + 66, y + 42, f"ΔDD {dd_improvement:+.1f}pp", size=12, fill=INK_2, anchor="middle", family=FONT_MONO))
        strict_row = strict_lookup[policy]
        body.append(_svg_text(1160, y + 33, f"{int(_num(strict_row['folds_passed']))}/4", size=14, fill=CORAL, weight=850, anchor="end", family=FONT_MONO))
    body.append(f'<rect x="470" y="740" width="674" height="54" rx="14" fill="#f8e1db"/>')
    body.append(_svg_text(492, 773, "更严格验证：全部 7 种 policy 均为 0/4 通过。方向有价值，不等于稳定准入。", size=16, fill=INK, weight=650))
    svg = _chart_shell(
        "“解决了”之后，还要再验证",
        "早期 gate 给出希望；加入更严格时间窗口后，结论被重新限定。",
        "".join(body),
        height=850,
        badges=[("US", MINT, INK), ("RESEARCH ONLY", PAPER_2, INK_2)],
        footer="Source: composite_advisory_phase1 + composite_stability_phase4_advisory",
    )
    return "07_advisory_gate.svg", svg, _manifest_item("07", "not_admitted_under_strict_gate", "US", sources)


def _manifest_item(chart_id: str, status: str, market: str, sources: list[dict[str, Any]]) -> dict[str, Any]:
    source_summary = json.dumps(sources, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {
        "id": chart_id,
        "status": status,
        "market": market,
        "source_summary_sha256": hashlib.sha256(source_summary).hexdigest(),
        "sources": sources,
    }


VIDEO_SPECS = [
    ("01_home", "首页市场镜头", "10 秒", ["首页稳定 2 秒", "切换 A 股 / 美股", "点击“换一只”", "停在完整市场镜头"]),
    ("02_single_entry", "单股分析入口", "12 秒", ["选择美股", "搜索 NVDA", "选择本地样例", "进入 K 线分析"]),
    ("03_single_analysis", "单股结果与比较", "15 秒", ["基础信息与指标", "切换策略区", "净值 / 回撤 / KPI", "切换策略比对"]),
    ("04_multi_entry", "多股分析入口", "12 秒", ["加入 NVDA / TSLA / META", "确认已选列表", "开始多股分析", "停在三股上下文"]),
    ("05_multi_analysis", "多股组合结果", "15 秒", ["归一化价格", "相关性", "组合曲线与 KPI", "个股贡献 / 热力图"]),
]


CHART_FAILURE_SPECS: dict[str, tuple[str, str, str, str, list[str]]] = {
    "_chart_01": (
        "01",
        "01_model_leaderboard.svg",
        "复杂度没有自动换来更强",
        "US / CN_A",
        [
            "model-test/outputs/full_us_deans_60/model_summary.csv",
            "model-test/outputs/full_cn_a_deans_60/model_summary.csv",
        ],
    ),
    "_chart_02": (
        "02",
        "02_transformer_stop.svg",
        "相似度提高，决策效用反而下降",
        "US",
        ["research/RESEARCH_CATALOG.json"],
    ),
    "_chart_03": (
        "03",
        "03_factor_selection.svg",
        "从“全都要”到五因子",
        "US",
        ["model-test/outputs/phase2_weight_optimization/optimization_results.json"],
    ),
    "_chart_04": (
        "04",
        "04_optimization_ladder.svg",
        "允许负权重后的优化跃迁",
        "US",
        [
            "model-test/outputs/phase2_weight_optimization/optimization_results.json",
            "model-test/outputs/phase2_5_advanced_optimization/advanced_optimization_results.json",
        ],
    ),
    "_chart_05": (
        "05",
        "05_cn_a_comparison.svg",
        "Composite 与 SM / FSM 的冻结比较",
        "CN_A",
        ["model-test/outputs/cn_a_factor_composite_comparison/comparison_metrics.csv"],
    ),
    "_chart_06": (
        "06",
        "06_saturation_diagnostic.svg",
        "为什么需要 Advisor：持仓饱和诊断",
        "US",
        [
            "model-test/outputs/composite_vs_sm_comparison/comparison_metrics.csv",
            "model-test/outputs/composite_vs_sm_comparison/README.md",
        ],
    ),
    "_chart_07": (
        "07",
        "07_advisory_gate.svg",
        "“解决了”之后，还要再验证",
        "US",
        [
            "model-test/outputs/composite_advisory_phase1/admission_summary.json",
            "model-test/outputs/composite_advisory_phase1/ablation_metrics.csv",
            "model-test/outputs/composite_stability_phase4_advisory/admission_summary.csv",
            "model-test/outputs/composite_stability_phase4_advisory/fold_metrics.csv",
        ],
    ),
}


def _poster_svg(title: str, duration: str, steps: list[str], index: int) -> str:
    step_markup: list[str] = []
    for step_index, step in enumerate(steps):
        x = 118 + step_index * 300
        step_markup.append(f'<circle cx="{x}" cy="620" r="26" fill="{VIOLET if step_index == 0 else CYAN}"/>')
        step_markup.append(_svg_text(x, 628, f"{step_index + 1:02d}", size=15, fill=PAPER, weight=800, anchor="middle", family=FONT_MONO))
        step_markup.append(_svg_text(x, 680, step, size=18, fill=INK, weight=650, anchor="middle"))
        if step_index < len(steps) - 1:
            step_markup.append(f'<line x1="{x + 36}" y1="620" x2="{x + 264}" y2="620" stroke="{LINE}" stroke-width="2"/>')
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1440 900" role="img" aria-label="{escape(title)}视频录制占位">
  <defs>
    <radialGradient id="glow{index}" cx="50%" cy="40%" r="64%"><stop offset="0" stop-color="{VIOLET_2}" stop-opacity=".22"/><stop offset="1" stop-color="{PAPER}" stop-opacity="0"/></radialGradient>
  </defs>
  <rect width="1440" height="900" fill="{PAPER_2}"/>
  <rect width="1440" height="900" fill="url(#glow{index})"/>
  <rect x="64" y="64" width="1312" height="772" rx="30" fill="{PAPER}" stroke="{LINE}"/>
  <rect x="64" y="64" width="1312" height="58" rx="30" fill="#ebe6db"/>
  <circle cx="102" cy="93" r="8" fill="{CORAL}"/><circle cx="128" cy="93" r="8" fill="{LIME}"/><circle cx="154" cy="93" r="8" fill="{CYAN}"/>
  {_svg_text(720, 99, 'strategy.local / recording-slot', size=16, fill=INK_3, anchor='middle', family=FONT_MONO)}
  {_badge(1195, 77, duration, fill=MINT, color=INK)}
  {_svg_text(104, 205, f'CLIP {index:02d}', size=16, fill=CYAN, weight=800, family=FONT_MONO, letter_spacing=2)}
  {_svg_text(104, 282, title, size=62, fill=INK, weight=600, family=FONT_SERIF)}
  {_svg_text(104, 330, '视频素材待录制；收到 MP4 后将替换本海报并保留低动态降级。', size=23, fill=INK_2)}
  <rect x="104" y="392" width="1232" height="120" rx="24" fill="#f4efe5"/>
  {_svg_text(720, 448, '1440 × 900 · 30 FPS · H.264 · MUTED · LIGHT THEME', size=22, fill=INK, weight=750, anchor='middle', family=FONT_MONO)}
  {_svg_text(720, 486, '前后各留 1 秒空镜，不录制 ws token 或个人信息', size=18, fill=INK_2, anchor='middle')}
  {''.join(step_markup)}
  {_svg_text(104, 792, 'PENDING MEDIA', size=15, fill=CORAL, weight=800, family=FONT_MONO, letter_spacing=2)}
</svg>
'''


def _build_outputs() -> tuple[dict[Path, str], dict[str, Any]]:
    outputs: dict[Path, str] = {}
    chart_manifest: list[dict[str, Any]] = []
    chart_builders = [_chart_01, _chart_02, _chart_03, _chart_04, _chart_05, _chart_06, _chart_07]
    for builder in chart_builders:
        try:
            filename, svg, manifest_item = builder()
        except (IndexError, KeyError, StopIteration, TypeError, ValueError, ZeroDivisionError):
            chart_id, filename, title, market, source_paths = CHART_FAILURE_SPECS[builder.__name__]
            sources = [_source(ROOT / source_path) for source_path in source_paths]
            svg = _unavailable_chart(
                title,
                sources,
                reason="冻结源字段缺失或格式无效，未生成替代数据",
            )
            manifest_item = _manifest_item(chart_id, "unavailable", market, sources)
        outputs[CHART_DIR / filename] = svg
        chart_manifest.append({**manifest_item, "file": f"charts/{filename}"})

    poster_manifest: list[dict[str, Any]] = []
    for index, (stem, title, duration, steps) in enumerate(VIDEO_SPECS, start=1):
        filename = f"{stem}.svg"
        outputs[POSTER_DIR / filename] = _poster_svg(title, duration, steps, index)
        poster_manifest.append(
            {
                "id": stem,
                "file": f"posters/{filename}",
                "video": f"video/{stem}.mp4",
                "duration": duration,
                "status": "pending_media",
            }
        )

    manifest = {
        "schema_version": 1,
        "policy": "missing sources remain unavailable; no zero-fill or cross-market substitution",
        "charts": chart_manifest,
        "videos": poster_manifest,
    }
    outputs[ASSET_ROOT / "chart_manifest.json"] = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    return outputs, manifest


def _write_outputs(outputs: dict[Path, str]) -> None:
    for path, content in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")


def _check_outputs(outputs: dict[Path, str]) -> list[str]:
    failures: list[str] = []
    for path, expected in outputs.items():
        if not path.exists():
            failures.append(f"missing: {path.relative_to(ROOT)}")
            continue
        actual = path.read_text(encoding="utf-8")
        if actual != expected:
            failures.append(f"stale: {path.relative_to(ROOT)}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Build deterministic charts and video posters for Strategy Research Story.")
    parser.add_argument("--check", action="store_true", help="Verify generated assets without rewriting them.")
    args = parser.parse_args()

    outputs, manifest = _build_outputs()
    unavailable = [item["id"] for item in manifest["charts"] if item["status"] == "unavailable"]
    if unavailable:
        print(f"warning: unavailable charts: {', '.join(unavailable)}", file=sys.stderr)

    if args.check:
        failures = _check_outputs(outputs)
        if failures:
            for failure in failures:
                print(failure, file=sys.stderr)
            return 1
        print(f"verified {len(outputs)} generated assets")
        return 0

    _write_outputs(outputs)
    print(f"generated {len(outputs)} assets under {ASSET_ROOT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
