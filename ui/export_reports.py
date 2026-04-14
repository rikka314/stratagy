"""
共享 HTML 导出报告 builder
=========================
为单股 / 多股页面生成符合 W6-W8 站点风格的离线 HTML 报告。
"""

from __future__ import annotations
from ui.i18n import tr

from datetime import datetime
import html
from typing import Any

import pandas as pd
import plotly.graph_objects as go


def _lang(language: str | None) -> str:
    return "en" if str(language or "zh").strip().lower() == "en" else "zh"


def _theme(theme: str | None) -> str:
    return "dark" if str(theme or "light").strip().lower() == "dark" else "light"


def _t(language: str, zh: str, en: str) -> str:
    return en if _lang(language) == "en" else zh


def _esc(value: object) -> str:
    return html.escape(str(value if value is not None else ""))


def _safe_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(numeric) else numeric


def _fmt_decimal(value: object, digits: int = 2) -> str:
    numeric = _safe_float(value)
    if numeric is None:
        return "N/A"
    return f"{numeric:,.{digits}f}"


def _fmt_pct(value: object, digits: int = 2, *, signed: bool = False) -> str:
    numeric = _safe_float(value)
    if numeric is None:
        return "N/A"
    sign = "+" if signed else ""
    return f"{numeric:{sign}.{digits}%}"


def _fmt_ratio(value: object, digits: int = 2) -> str:
    numeric = _safe_float(value)
    if numeric is None:
        return "N/A"
    return f"{numeric:.{digits}f}"


def _fmt_compact_number(value: object) -> str:
    numeric = _safe_float(value)
    if numeric is None:
        return "N/A"
    absolute = abs(numeric)
    if absolute >= 1_000_000_000:
        return f"{numeric / 1_000_000_000:.2f}B"
    if absolute >= 1_000_000:
        return f"{numeric / 1_000_000:.2f}M"
    if absolute >= 1_000:
        return f"{numeric / 1_000:.2f}K"
    return f"{numeric:,.0f}"


def _fmt_date(value: object) -> str:
    timestamp = pd.to_datetime(value, errors="coerce")
    if pd.isna(timestamp):
        return "N/A"
    return timestamp.strftime("%Y-%m-%d")


def _fmt_generated_at(value: datetime | None, language: str) -> str:
    timestamp = value or datetime.now()
    if _lang(language) == "en":
        return timestamp.strftime("%Y-%m-%d %H:%M:%S")
    return timestamp.strftime(tr("dateTime.formatLong"))


def _build_css(theme: str) -> str:
    if _theme(theme) == "dark":
        bg_canvas = "#17120f"
        bg_glow = "rgba(224, 161, 108, 0.14)"
        surface_main = "rgba(28, 23, 19, 0.96)"
        surface_sheet = "rgba(39, 32, 27, 0.92)"
        surface_line = "rgba(242, 231, 217, 0.12)"
        surface_line_strong = "rgba(242, 231, 217, 0.18)"
        text_strong = "#f4e9db"
        text_primary = "#ead8c6"
        text_secondary = "#c9b29a"
        text_muted = "#a6886d"
        accent_warm = "#e0a16c"
        hero_band = "linear-gradient(140deg, rgba(58, 46, 37, 0.96), rgba(25, 20, 17, 0.98))"
        metric_fill = "linear-gradient(145deg, rgba(224, 161, 108, 0.28), rgba(84, 67, 52, 0.42))"
        shadow = "0 26px 70px rgba(0, 0, 0, 0.34)"
    else:
        bg_canvas = "#f7f1e8"
        bg_glow = "rgba(219, 170, 120, 0.24)"
        surface_main = "rgba(255, 252, 247, 0.96)"
        surface_sheet = "rgba(255, 248, 239, 0.92)"
        surface_line = "rgba(123, 95, 64, 0.10)"
        surface_line_strong = "rgba(123, 95, 64, 0.18)"
        text_strong = "#2d2117"
        text_primary = "#493527"
        text_secondary = "#6d5540"
        text_muted = "#92755a"
        accent_warm = "#ba7349"
        hero_band = "linear-gradient(140deg, rgba(255, 251, 245, 0.98), rgba(246, 233, 213, 0.98))"
        metric_fill = "linear-gradient(145deg, rgba(255, 241, 225, 0.96), rgba(244, 229, 210, 0.92))"
        shadow = "0 24px 64px rgba(117, 86, 54, 0.12)"

    return f"""
:root {{
  --bg-canvas: {bg_canvas};
  --bg-glow: {bg_glow};
  --surface-main: {surface_main};
  --surface-sheet: {surface_sheet};
  --surface-line: {surface_line};
  --surface-line-strong: {surface_line_strong};
  --text-strong: {text_strong};
  --text-primary: {text_primary};
  --text-secondary: {text_secondary};
  --text-muted: {text_muted};
  --accent-warm: {accent_warm};
  --hero-band: {hero_band};
  --metric-fill: {metric_fill};
  --shadow-main: {shadow};
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  color: var(--text-primary);
  background:
    radial-gradient(circle at top right, var(--bg-glow), transparent 32%),
    radial-gradient(circle at left 12% bottom 10%, rgba(126, 194, 141, 0.08), transparent 26%),
    var(--bg-canvas);
  font-family: "Avenir Next", "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
  line-height: 1.65;
}}
.export-shell {{
  max-width: 1280px;
  margin: 0 auto;
  padding: 32px 24px 64px;
}}
.export-hero, .paper-block, .chart-card {{
  border: 1px solid var(--surface-line);
  box-shadow: 0 16px 42px rgba(0, 0, 0, 0.06);
}}
.export-hero {{
  padding: 30px 32px 28px;
  border-radius: 32px;
  background: var(--hero-band);
  box-shadow: var(--shadow-main);
}}
.hero-kicker, .section-kicker, .stat-label, thead th {{
  font-size: 0.78rem;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}}
.hero-kicker {{ color: var(--accent-warm); }}
.hero-title {{
  margin: 0.55rem 0 0;
  color: var(--text-strong);
  font-family: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", Georgia, serif;
  font-size: clamp(2.1rem, 3.6vw, 3.45rem);
  line-height: 0.98;
  letter-spacing: -0.04em;
}}
.hero-copy, .section-copy, .chart-copy, .kv-meta, .stat-meta {{
  color: var(--text-secondary);
}}
.chip-row, .badge-row {{
  display: flex;
  flex-wrap: wrap;
  gap: 0.55rem;
}}
.chip-row {{ margin-top: 1rem; }}
.chip, .inline-badge {{
  display: inline-flex;
  align-items: center;
  min-height: 32px;
  padding: 0.38rem 0.72rem;
  border-radius: 999px;
  border: 1px solid var(--surface-line-strong);
  background: rgba(255, 255, 255, 0.05);
  color: var(--text-secondary);
  font-size: 0.82rem;
  font-weight: 700;
}}
.chip.accent {{ color: var(--accent-warm); }}
.stat-grid {{
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0.9rem;
  margin-top: 1.1rem;
}}
.stat-card, .kv-item {{
  min-width: 0;
  border: 1px solid var(--surface-line);
  border-radius: 22px;
}}
.stat-card {{
  padding: 1rem 1.05rem;
  background: var(--metric-fill);
}}
.stat-value, .kv-value, .section-title, .chart-title {{
  color: var(--text-strong);
  font-weight: 800;
}}
.stat-value {{
  display: block;
  margin-top: 0.4rem;
  font-size: 1.15rem;
  line-height: 1.35;
  overflow-wrap: anywhere;
}}
.report-grid {{
  display: grid;
  grid-template-columns: minmax(0, 0.95fr) minmax(0, 1.05fr);
  gap: 1rem;
  margin-top: 1.15rem;
}}
.paper-block {{
  min-width: 0;
  padding: 1.2rem 1.24rem;
  border-radius: 28px;
  background: var(--surface-main);
}}
.section-title {{
  margin: 0.35rem 0 0;
  font-size: 1.28rem;
}}
.kv-grid {{
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.8rem;
  margin-top: 1rem;
}}
.kv-item {{
  padding: 0.92rem 0.96rem;
  background: var(--surface-sheet);
}}
.table-shell {{
  margin-top: 1rem;
  overflow-x: auto;
  border: 1px solid var(--surface-line);
  border-radius: 22px;
  background: var(--surface-sheet);
}}
table {{
  width: 100%;
  min-width: 720px;
  border-collapse: collapse;
}}
thead th {{
  padding: 0.88rem 0.9rem;
  text-align: left;
  border-bottom: 1px solid var(--surface-line-strong);
  color: var(--text-muted);
}}
tbody td {{
  padding: 0.92rem 0.9rem;
  border-bottom: 1px solid var(--surface-line);
  font-size: 0.92rem;
}}
tbody tr:last-child td {{ border-bottom: none; }}
.swatch {{
  display: inline-block;
  width: 0.72rem;
  height: 0.72rem;
  margin-right: 0.55rem;
  border-radius: 999px;
  vertical-align: middle;
}}
.section-stack {{
  display: grid;
  gap: 1rem;
  margin-top: 1rem;
}}
.chart-grid {{
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1rem;
}}
.chart-card {{
  min-width: 0;
  padding: 1rem;
  border-radius: 28px;
  background: var(--surface-main);
}}
.chart-card.wide {{ grid-column: 1 / -1; }}
.plot-host {{
  width: 100%;
  min-height: 420px;
  margin-top: 0.8rem;
}}
.plot-host.tall {{ min-height: 560px; }}
.footer {{
  margin-top: 1rem;
  padding: 1rem 1.05rem 0;
  color: var(--text-muted);
  font-size: 0.82rem;
}}
@media (max-width: 980px) {{
  .stat-grid, .report-grid, .chart-grid, .kv-grid {{
    grid-template-columns: 1fr;
  }}
  .export-shell {{ padding-inline: 18px; }}
  .export-hero, .paper-block, .chart-card {{ border-radius: 24px; }}
  .plot-host, .plot-host.tall {{ min-height: 380px; }}
}}
@media (max-width: 680px) {{
  .export-shell {{ padding: 20px 14px 42px; }}
  .export-hero, .paper-block, .chart-card {{ padding: 1rem; }}
  .hero-title {{ font-size: 2.15rem; }}
  table {{ min-width: 620px; }}
  .plot-host, .plot-host.tall {{ min-height: 320px; }}
}}
.model-analysis-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 1rem;
  margin-top: 1rem;
}}
.model-analysis-card {{
  border: 1px solid var(--surface-line);
  border-radius: 22px;
  background: var(--surface-sheet);
  padding: 1rem 1.1rem;
}}
.model-analysis-header {{
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.8rem;
  font-size: 1.05rem;
}}
.model-badge {{
  display: inline-block;
  padding: 0.15rem 0.55rem;
  border-radius: 999px;
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}}
.model-badge.best {{
  background: var(--accent-warm);
  color: #fff;
}}
.model-analysis-body {{
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.8rem;
}}
.analysis-column h4 {{
  margin: 0 0 0.4rem;
  font-size: 0.82rem;
  font-weight: 800;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--text-muted);
}}
.strength-list, .weakness-list {{
  margin: 0;
  padding-left: 1.1rem;
  font-size: 0.85rem;
  line-height: 1.55;
  color: var(--text-secondary);
}}
.strength-list li {{ color: #4a8c5c; }}
.weakness-list li {{ color: #b85c3a; }}
.underperform-block {{
  margin-top: 0.8rem;
  padding-top: 0.7rem;
  border-top: 1px solid var(--surface-line);
}}
.underperform-block h4 {{
  margin: 0 0 0.35rem;
  font-size: 0.82rem;
  font-weight: 800;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--text-muted);
}}
.underperform-block ul {{
  margin: 0;
  padding-left: 1.1rem;
  font-size: 0.85rem;
  line-height: 1.55;
  color: var(--text-secondary);
}}
@media (max-width: 680px) {{
  .model-analysis-body {{ grid-template-columns: 1fr; }}
  .model-analysis-grid {{ grid-template-columns: 1fr; }}
}}
/* ── Stock insight cards (per-stock portfolio analysis) ────────────── */
.stock-insight-card {{
  padding: 1.1rem 1.2rem;
  border-radius: 18px;
  background: var(--surface-sheet);
  border: 1px solid var(--surface-line);
}}
.stock-insight-card.insight-positive {{ border-left: 4px solid #22c55e; }}
.stock-insight-card.insight-negative {{ border-left: 4px solid #ef4444; }}
.stock-insight-card.insight-neutral  {{ border-left: 4px solid #94a3b8; }}
.stock-insight-header {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.5rem;
}}
.stock-weight-badge {{
  display: inline-block;
  padding: 0.18rem 0.65rem;
  font-size: 0.78rem;
  border-radius: 999px;
  background: var(--surface-main);
  color: var(--text-muted);
}}
.stock-insight-list {{
  margin: 0.4rem 0 0.6rem 1.1rem;
  padding: 0;
  font-size: 0.88rem;
  line-height: 1.55;
  color: var(--text-main);
}}
.stock-insight-list li {{ margin-bottom: 0.3rem; }}
.stock-insight-metrics {{
  display: flex;
  gap: 1.2rem;
  font-size: 0.82rem;
  color: var(--text-muted);
  border-top: 1px solid var(--surface-line);
  padding-top: 0.5rem;
  margin-top: 0.3rem;
}}
"""


def _get_plotly_js_inline() -> str:
    """Read the local plotly.min.js bundled with the plotly package for offline use."""
    try:
        import plotly
        import os
        js_path = os.path.join(os.path.dirname(plotly.__file__), "package_data", "plotly.min.js")
        if os.path.exists(js_path):
            with open(js_path, "r", encoding="utf-8") as f:
                return f"<script>{f.read()}</script>"
    except Exception:
        pass
    # fallback to CDN if local file not available
    return '<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>'


def _build_head(title: str, theme: str, language: str) -> str:
    plotly_tag = _get_plotly_js_inline()
    return f"""<!DOCTYPE html>
<html lang="{'en' if _lang(language) == 'en' else 'zh-CN'}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{_esc(title)}</title>
  {plotly_tag}
  <style>{_build_css(theme)}</style>
</head>
<body data-theme="{_esc(_theme(theme))}">
  <main class="export-shell">
"""


def _build_footer(language: str) -> str:
    return f"""
    <footer class="footer">
      <div>{_esc(_t(language, tr("export.description"), "Exported by Strategy Lab with the same frontend grammar as the main analysis site."))}</div>
      <div>{_esc(_t(language, tr("chart.plotlyNote"), "Charts are rendered with Plotly and remain responsive when opened offline."))}</div>
    </footer>
  </main>
</body>
</html>
"""


def _build_stat_cards(cards: list[dict[str, str]]) -> str:
    return "".join(
        f"""
<article class="stat-card">
  <span class="stat-label">{_esc(card["label"])}</span>
  <span class="stat-value">{_esc(card["value"])}</span>
  <span class="stat-meta">{_esc(card.get("meta", ""))}</span>
</article>
"""
        for card in cards
    )


def _build_kv_items(items: list[dict[str, str]]) -> str:
    return "".join(
        f"""
<div class="kv-item">
  <span class="stat-label">{_esc(item["label"])}</span>
  <span class="kv-value">{_esc(item["value"])}</span>
  <span class="kv-meta">{_esc(item.get("meta", ""))}</span>
</div>
"""
        for item in items
    )


def _build_table(headers: list[str], rows: list[list[str]]) -> str:
    header_html = "".join(f"<th>{_esc(header)}</th>" for header in headers)
    row_html = "".join(
        "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>"
        for row in rows
    )
    return f"""
<div class="table-shell">
  <table>
    <thead><tr>{header_html}</tr></thead>
    <tbody>{row_html}</tbody>
  </table>
</div>
"""


def _plot_card_markup(
    *,
    plot_id: str,
    title: str,
    copy: str = "",
    wide: bool = False,
    tall: bool = False,
) -> str:
    card_class = "chart-card wide" if wide else "chart-card"
    host_class = "plot-host tall" if tall else "plot-host"
    copy_html = f'  <p class="chart-copy">{_esc(copy)}</p>\n' if copy else ""
    return f"""
<article class="{card_class}">
  <div class="chart-title">{_esc(title)}</div>
{copy_html}  <div id="{_esc(plot_id)}" class="{host_class}"></div>
</article>
"""


def _plot_script(plot_id: str, fig: go.Figure) -> str:
    js_var = plot_id.replace("-", "_")
    return f"""
<script>
const {js_var} = {fig.to_json()};
Plotly.newPlot("{plot_id}", {js_var}.data, {js_var}.layout, {{
  responsive: true,
  displaylogo: false
}});
</script>
"""


def _build_model_analysis_html(export_payloads: list[dict], language: str) -> str:
    """Generate comparative model analysis HTML with strengths/weaknesses."""
    if not export_payloads or len(export_payloads) < 2:
        return ""

    # Find best model by Sharpe
    best_idx = 0
    best_sharpe = -999.0
    for i, p in enumerate(export_payloads):
        ev = p.get("eval") or {}
        s = _safe_float(ev.get("sharpe"))
        if s is not None and s > best_sharpe:
            best_sharpe = s
            best_idx = i

    analysis_cards = []
    for i, payload in enumerate(export_payloads):
        ev = payload.get("eval") or {}
        label = str(payload.get("short_label") or "Model")
        color = _esc(payload.get("color") or "#ba7349")
        is_best = (i == best_idx)

        cumret = _safe_float(ev.get("cumret"))
        annret = _safe_float(ev.get("annret"))
        maxdd = _safe_float(ev.get("maxdd"))
        sharpe = _safe_float(ev.get("sharpe"))
        winrate = _safe_float(ev.get("winrate"))
        pnl = _safe_float(ev.get("pnl_ratio"))

        strengths: list[str] = []
        weaknesses: list[str] = []
        underperform_reasons: list[str] = []

        # Sharpe analysis
        if sharpe is not None:
            if sharpe > 1.0:
                strengths.append(_t(language, "夏普比率优异 (>1.0)，风险调整后回报出色", "Excellent Sharpe ratio (>1.0), outstanding risk-adjusted returns"))
            elif sharpe > 0.5:
                strengths.append(_t(language, "夏普比率良好 (>0.5)，风险调整后回报合理", "Good Sharpe ratio (>0.5), reasonable risk-adjusted returns"))
            elif sharpe > 0:
                weaknesses.append(_t(language, "夏普比率偏低 (<0.5)，风险调整后回报不理想", "Low Sharpe ratio (<0.5), suboptimal risk-adjusted returns"))
            else:
                weaknesses.append(_t(language, "夏普比率为负，策略亏损", "Negative Sharpe ratio, strategy is losing"))

        # Win rate analysis
        if winrate is not None:
            if winrate > 0.55:
                strengths.append(_t(language, f"胜率较高 ({winrate:.0%})，交易一致性好", f"High win rate ({winrate:.0%}), good trading consistency"))
            elif winrate < 0.4:
                weaknesses.append(_t(language, f"胜率偏低 ({winrate:.0%})，多数交易亏损", f"Low win rate ({winrate:.0%}), majority of trades are losses"))

        # Max drawdown analysis
        if maxdd is not None:
            if abs(maxdd) < 0.1:
                strengths.append(_t(language, f"最大回撤较小 ({maxdd:.1%})，风险控制良好", f"Small max drawdown ({maxdd:.1%}), good risk control"))
            elif abs(maxdd) > 0.3:
                weaknesses.append(_t(language, f"最大回撤较大 ({maxdd:.1%})，存在较大亏损风险", f"Large max drawdown ({maxdd:.1%}), significant loss risk"))

        # Cumulative return analysis
        if cumret is not None:
            if cumret > 0.2:
                strengths.append(_t(language, f"累计收益可观 ({cumret:.1%})", f"Substantial cumulative return ({cumret:.1%})"))
            elif cumret < 0:
                weaknesses.append(_t(language, f"累计收益为负 ({cumret:.1%})", f"Negative cumulative return ({cumret:.1%})"))

        # PnL ratio
        if pnl is not None:
            if pnl > 1.5:
                strengths.append(_t(language, f"盈亏比优秀 ({pnl:.2f})，盈利交易平均收益远大于亏损", f"Excellent PnL ratio ({pnl:.2f}), average gain far exceeds average loss"))
            elif pnl < 1.0:
                weaknesses.append(_t(language, f"盈亏比不足 ({pnl:.2f})，需要更高胜率弥补", f"Poor PnL ratio ({pnl:.2f}), requires higher win rate to compensate"))

        # Underperformance reasons vs best
        if not is_best and best_sharpe > -999:
            best_ev = (export_payloads[best_idx].get("eval") or {})
            best_label = str(export_payloads[best_idx].get("short_label") or "Best")

            if sharpe is not None and best_sharpe is not None and best_sharpe > sharpe:
                diff = best_sharpe - sharpe
                underperform_reasons.append(_t(language,
                    f"夏普比率低于 {best_label} {diff:.2f}，风险调整后回报差距明显",
                    f"Sharpe ratio is {diff:.2f} lower than {best_label}, notable gap in risk-adjusted returns"))

            best_cumret = _safe_float(best_ev.get("cumret"))
            if cumret is not None and best_cumret is not None and best_cumret > cumret:
                underperform_reasons.append(_t(language,
                    f"累计收益落后 {best_label} {(best_cumret - cumret):.1%}",
                    f"Cumulative return trails {best_label} by {(best_cumret - cumret):.1%}"))

            best_maxdd = _safe_float(best_ev.get("maxdd"))
            if maxdd is not None and best_maxdd is not None and abs(maxdd) > abs(best_maxdd) * 1.2:
                underperform_reasons.append(_t(language,
                    f"回撤控制不如 {best_label}，最大回撤更深 {abs(maxdd) - abs(best_maxdd):.1%}",
                    f"Weaker drawdown control than {best_label}, max drawdown deeper by {abs(maxdd) - abs(best_maxdd):.1%}"))

        badge = f"<span class='model-badge best'>{_t(language, '最佳', 'Best')}</span>" if is_best else ""
        strengths_html = "".join(f"<li>{_esc(s)}</li>" for s in strengths) if strengths else f"<li>{_t(language, '无显著优势', 'No notable strengths')}</li>"
        weaknesses_html = "".join(f"<li>{_esc(w)}</li>" for w in weaknesses) if weaknesses else f"<li>{_t(language, '无明显劣势', 'No notable weaknesses')}</li>"
        underperform_html = ""
        if underperform_reasons:
            reasons = "".join(f"<li>{_esc(r)}</li>" for r in underperform_reasons)
            underperform_html = f"""
            <div class="underperform-block">
              <h4>{_t(language, '为什么该模型表现较弱', 'Why this model underperforms')}</h4>
              <ul>{reasons}</ul>
            </div>"""

        analysis_cards.append(f"""
        <div class="model-analysis-card">
          <div class="model-analysis-header">
            <span class="swatch" style="background:{color}"></span>
            <strong>{_esc(label)}</strong> {badge}
          </div>
          <div class="model-analysis-body">
            <div class="analysis-column">
              <h4>{_t(language, '优势', 'Strengths')}</h4>
              <ul class="strength-list">{strengths_html}</ul>
            </div>
            <div class="analysis-column">
              <h4>{_t(language, '劣势', 'Weaknesses')}</h4>
              <ul class="weakness-list">{weaknesses_html}</ul>
            </div>
          </div>
          {underperform_html}
        </div>""")

    return "".join(analysis_cards)


def build_single_stock_export_html(
    *,
    title: str,
    symbol: str,
    stock_name: str = "",
    market: str = "",
    currency: str = "",
    df: pd.DataFrame,
    test_df: pd.DataFrame | None,
    model_payload: dict[str, dict],
    active_models: list[str],
    candle: go.Figure,
    ind_fig: go.Figure,
    score_fig: go.Figure,
    equity_fig: go.Figure,
    signal_fig: go.Figure,
    suggestion: str,
    indicator_title: str,
    include_date: bool,
    language: str = "zh",
    theme: str = "light",
    generated_at: datetime | None = None,
    ticker_info: dict | None = None,
) -> str:
    language = _lang(language)
    theme = _theme(theme)
    export_models = [name for name in active_models if name in model_payload]
    export_payloads = [model_payload[name] for name in export_models]

    # ── 基础行情数据 ──────────────────────────────────────────────────────────
    latest_close = _safe_float(df["close"].iloc[-1]) if not df.empty and "close" in df.columns else None
    previous_close = _safe_float(df["close"].iloc[-2]) if len(df) > 1 and "close" in df.columns else None
    change_pct = None if latest_close is None or previous_close in {None, 0} else latest_close / previous_close - 1.0
    test_rows = len(test_df) if test_df is not None else 0
    train_rows = max(len(df) - test_rows, 0)
    date_min = _fmt_date(df["date"].min()) if "date" in df.columns and not df.empty else "N/A"
    date_max = _fmt_date(df["date"].max()) if "date" in df.columns and not df.empty else "N/A"

    # ── 策略评估数据 ──────────────────────────────────────────────────────────
    if export_payloads:
        main_eval = dict(export_payloads[0].get("eval") or {})
        export_model_text = ", ".join(str(payload.get("short_label") or "Model") for payload in export_payloads)
        summary_rows = [
            [
                f"<span class='swatch' style='background:{_esc(payload.get('color') or '#ba7349')}'></span>{_esc(payload.get('short_label') or 'Model')}",
                _esc(_fmt_pct((payload.get("eval") or {}).get("cumret"))),
                _esc(_fmt_pct((payload.get("eval") or {}).get("annret"))),
                _esc(_fmt_pct((payload.get("eval") or {}).get("maxdd"))),
                _esc(_fmt_ratio((payload.get("eval") or {}).get("sharpe"))),
                _esc(_fmt_pct((payload.get("eval") or {}).get("winrate"))),
                _esc(_fmt_ratio((payload.get("eval") or {}).get("pnl_ratio"))),
            ]
            for payload in export_payloads
        ]
    else:
        strategy_ret = None
        benchmark_ret = None
        if test_df is not None and not test_df.empty:
            strategy_ret = _safe_float(test_df["strategy_equity"].iloc[-1]) - 1.0 if "strategy_equity" in test_df.columns else None
            benchmark_ret = _safe_float(test_df["buy_hold_equity"].iloc[-1]) - 1.0 if "buy_hold_equity" in test_df.columns else None
        main_eval = {"cumret": strategy_ret, "annret": None, "maxdd": None, "sharpe": None}
        export_model_text = _t(language, "无策略", "No strategy")
        summary_rows = [[
            _esc(_t(language, tr("strategy.current"), "Current strategy")),
            _esc(_fmt_pct(strategy_ret)),
            "N/A", "N/A", "N/A", "N/A",
            _esc(_fmt_pct(benchmark_ret)),
        ]]

    # ── Hero stat cards ───────────────────────────────────────────────────────
    cards = [
        {
            "label": _t(language, tr("price.latest_close"), "Latest close"),
            "value": _fmt_decimal(latest_close),
            "meta": _t(language, f"最新涨跌 {_fmt_pct(change_pct, signed=True)}", f"Latest move {_fmt_pct(change_pct, signed=True)}"),
        },
        {
            "label": _t(language, tr("action.exportModel"), "Exported models"),
            "value": export_model_text,
            "meta": _t(language, f"{len(export_payloads) or 1} 条策略结果", f"{len(export_payloads) or 1} strategy result(s)"),
        },
        {
            "label": _t(language, tr("phase.train_test"), "Train / test"),
            "value": f"{train_rows} / {test_rows}",
            "meta": _t(language, f"共 {len(df)} 行数据", f"{len(df)} rows total"),
        },
        {
            "label": _t(language, tr("data.range"), "Data range"),
            "value": f"{date_min} – {date_max}",
            "meta": _t(language, f"{len(df)} 行价格数据", f"{len(df)} rows of price data"),
        },
    ]

    # ── Overview kv items ─────────────────────────────────────────────────────
    overview_items = [
        {
            "label": _t(language, tr("suggestions.current"), "Current suggestion"),
            "value": suggestion or "N/A",
            "meta": "",
        },
        {
            "label": _t(language, tr("price.latestOHL"), "Latest open / high / low"),
            "value": (
                f"{_fmt_decimal(df['open'].iloc[-1] if 'open' in df.columns and not df.empty else None)}"
                f" / {_fmt_decimal(df['high'].iloc[-1] if 'high' in df.columns and not df.empty else None)}"
                f" / {_fmt_decimal(df['low'].iloc[-1] if 'low' in df.columns and not df.empty else None)}"
            ),
            "meta": "",
        },
        {
            "label": _t(language, tr("market.latestVolume"), "Latest volume"),
            "value": _fmt_compact_number(df["volume"].iloc[-1] if "volume" in df.columns and not df.empty else None),
            "meta": "",
        },
        {
            "label": _t(language, tr("metrics.core_metrics"), "Key metrics"),
            "value": f"{_t(language, tr('returns.cumulative'), 'Total return')} {_fmt_pct(main_eval.get('cumret'))}",
            "meta": (
                f"{_t(language, tr('kpi.sharpe'), 'Sharpe')} {_fmt_ratio(main_eval.get('sharpe'))}"
                f" · {_t(language, tr('metrics.max_drawdown'), 'Max drawdown')} {_fmt_pct(main_eval.get('maxdd'))}"
            ),
        },
    ]

    # ── Model summary table ───────────────────────────────────────────────────
    summary_table = _build_table(
        [
            _t(language, tr("common.model"), "Model"),
            _t(language, tr("returns.cumulativeRate"), "Total return"),
            _t(language, tr("metrics.annualizedReturn"), "Annualized return"),
            _t(language, tr("metrics.max_drawdown"), "Max drawdown"),
            _t(language, tr("kpi.sharpe"), "Sharpe"),
            _t(language, tr("metric.win_rate"), "Win rate"),
            _t(language, tr("performance.profitLossRatioVsBenchmark"), "PnL ratio / Benchmark"),
        ],
        summary_rows,
    )

    # ── Chips ─────────────────────────────────────────────────────────────────
    chips = [
        _t(language, tr("report.singleStockExport"), "Single-stock export report"),
        symbol,
        _t(language, tr("report.offlineHtml"), "Offline HTML"),
    ]
    if include_date:
        chips.append(f"{_t(language, tr('meta.generatedTime'), 'Generated at')} {_fmt_generated_at(generated_at, language)}")

    # ── Assemble HTML ─────────────────────────────────────────────────────────
    html_parts = [_build_head(title, theme, language)]

    # Hero + overview + model summary
    html_parts.append(f"""
    <section class="export-hero">
      <div class="hero-kicker">Strategy Lab Report</div>
      <h1 class="hero-title">{_esc(title)}</h1>
      <div class="chip-row">{"".join(f"<span class='chip{' accent' if i == 0 else ''}'>{_esc(c)}</span>" for i, c in enumerate(chips))}</div>
      <div class="stat-grid">{_build_stat_cards(cards)}</div>
    </section>
    <section class="report-grid">
      <article class="paper-block">
        <div class="section-kicker">{_esc(_t(language, "概览", "Overview"))}</div>
        <h2 class="section-title">{_esc(_t(language, tr("section.strategy_overview"), "Strategy overview"))}</h2>
        <div class="kv-grid">{_build_kv_items(overview_items)}</div>
      </article>
      <article class="paper-block">
        <div class="section-kicker">{_esc(_t(language, "策略汇总", "Model Summary"))}</div>
        <h2 class="section-title">{_esc(_t(language, tr("analysis.model_summary_table"), "Model summary table"))}</h2>
        {summary_table}
      </article>
    </section>
""")

    # ── Stock profile section ─────────────────────────────────────────────────
    info = ticker_info or {}
    market_display = {"US": "US Stock (NYSE/NASDAQ)", "CN_A": "A-Share (SSE/SZSE)", "A": "A-Share (SSE/SZSE)"}.get(market, market or "N/A")
    currency_display = currency or ("USD" if market == "US" else "CNY" if market in ("A", "CN_A") else "N/A")
    avg_volume = _fmt_compact_number(df["volume"].mean() if "volume" in df.columns and not df.empty else None)

    # 52-week high/low: last 252 trading rows (not full dataset max/min)
    rows_252 = df.tail(252) if len(df) >= 252 else df
    high_52w = _fmt_decimal(rows_252["high"].max() if "high" in rows_252.columns and not rows_252.empty else None)
    low_52w = _fmt_decimal(rows_252["low"].min() if "low" in rows_252.columns and not rows_252.empty else None)

    # Computed OHLCV statistics
    total_return: float | None = None
    ann_return: float | None = None
    ann_vol: float | None = None
    max_dd_val: float | None = None
    if not df.empty and "close" in df.columns and len(df) > 2:
        closes = df["close"].dropna()
        if len(closes) > 2 and float(closes.iloc[0]) != 0:
            total_return = float(closes.iloc[-1]) / float(closes.iloc[0]) - 1.0
            n_days = len(closes)
            ann_return = (1.0 + total_return) ** (252.0 / n_days) - 1.0
        daily_ret = closes.pct_change().dropna()
        if len(daily_ret) > 1:
            ann_vol = float(daily_ret.std()) * (252 ** 0.5)
        roll_max = closes.cummax()
        drawdown = closes / roll_max - 1.0
        max_dd_val = float(drawdown.min())

    # Base profile items (always shown)
    stock_profile_items: list[dict] = [
        {"label": _t(language, "代码", "Symbol"), "value": symbol, "meta": stock_name or ""},
        {"label": _t(language, "市场", "Market"), "value": market_display, "meta": _t(language, f"币种：{currency_display}", f"Currency: {currency_display}")},
        {"label": _t(language, "数据区间", "Data Range"), "value": f"{date_min} – {date_max}", "meta": _t(language, f"共 {len(df)} 个交易日", f"{len(df)} trading days")},
        {"label": _t(language, "最新收盘价", "Latest Close"), "value": _fmt_decimal(latest_close), "meta": _t(language, f"涨跌 {_fmt_pct(change_pct, signed=True)}", f"Move {_fmt_pct(change_pct, signed=True)}")},
        {"label": _t(language, "52周高/低", "52-Week H/L"), "value": f"{high_52w} / {low_52w}", "meta": _t(language, f"均量 {avg_volume}", f"Avg vol {avg_volume}")},
        {"label": _t(language, "区间总回报", "Period Return"), "value": _fmt_pct(total_return, signed=True), "meta": _t(language, f"年化 {_fmt_pct(ann_return, signed=True)}", f"Annualized {_fmt_pct(ann_return, signed=True)}")},
        {"label": _t(language, "年化波动率", "Ann. Volatility"), "value": _fmt_pct(ann_vol), "meta": ""},
        {"label": _t(language, "最大回撤", "Max Drawdown"), "value": _fmt_pct(max_dd_val, signed=True), "meta": _t(language, "区间内最大峰谷跌幅", "Peak-to-trough over data period")},
    ]

    # Optional fundamental items from ticker_info (yfinance / caller-supplied)
    sector = str(info.get("sector") or "").strip()
    industry = str(info.get("industry") or "").strip()
    market_cap = info.get("market_cap") or info.get("marketCap")
    pe_ratio = info.get("pe_ratio") or info.get("trailingPE")
    beta = info.get("beta")
    div_yield = info.get("dividend_yield") or info.get("dividendYield")
    country = str(info.get("country") or "").strip()
    employees = info.get("employees") or info.get("fullTimeEmployees")
    description = str(info.get("description") or info.get("longBusinessSummary") or "").strip()

    if sector or industry:
        stock_profile_items.append({
            "label": _t(language, "所属行业", "Sector / Industry"),
            "value": sector or "N/A",
            "meta": industry or "",
        })
    if market_cap is not None:
        stock_profile_items.append({
            "label": _t(language, "市值", "Market Cap"),
            "value": _fmt_compact_number(market_cap),
            "meta": _t(language, f"P/E {_fmt_ratio(pe_ratio)}", f"P/E {_fmt_ratio(pe_ratio)}"),
        })
    if beta is not None or div_yield is not None:
        stock_profile_items.append({
            "label": _t(language, "Beta / 股息率", "Beta / Div. Yield"),
            "value": _fmt_ratio(beta),
            "meta": _fmt_pct(div_yield) if div_yield is not None else "N/A",
        })
    if country or employees is not None:
        stock_profile_items.append({
            "label": _t(language, "国家 / 员工数", "Country / Employees"),
            "value": country or "N/A",
            "meta": _fmt_compact_number(employees) if employees is not None else "",
        })

    description_block = ""
    if description:
        description_block = f"""
      <p class="section-copy" style="margin-top:0.75rem;font-size:0.78rem;line-height:1.55;color:var(--text-secondary);">{_esc(description[:600] + ("…" if len(description) > 600 else ""))}</p>"""

    html_parts.append(f"""
    <section class="section-stack">
      <article class="paper-block">
        <div class="section-kicker">{_esc(_t(language, "股票概览", "Stock Profile"))}</div>
        <h2 class="section-title">{_esc(_t(language, "标的基本信息", "Instrument Information"))}</h2>
        <div class="kv-grid">{_build_kv_items(stock_profile_items)}</div>{description_block}
      </article>
    </section>
""")

    # ── Model comparison analysis ─────────────────────────────────────────────
    model_analysis_html = _build_model_analysis_html(export_payloads, language)
    if model_analysis_html:
        html_parts.append(f"""
    <section class="section-stack">
      <article class="paper-block">
        <div class="section-kicker">{_esc(_t(language, "模型分析", "Model Analysis"))}</div>
        <h2 class="section-title">{_esc(_t(language, "模型对比分析", "Model Comparison Analysis"))}</h2>
        <p class="section-copy">{_esc(_t(language, "基于各模型的回测评估指标，自动分析每个模型的优势、劣势及表现差异原因。", "Automated analysis of each model's strengths, weaknesses, and performance difference based on backtest metrics."))}</p>
        <div class="model-analysis-grid">
          {model_analysis_html}
        </div>
      </article>
    </section>
""")

    # Charts section — only render cards for figures that have traces
    chart_cards_html = ""
    chart_scripts = []

    if bool(candle.data):
        chart_cards_html += _plot_card_markup(
            plot_id="single-candle-chart",
            title=_t(language, tr("chart.candlestick_main"), "Candlestick"),
            wide=True, tall=True,
        )
        chart_scripts.append(_plot_script("single-candle-chart", candle))

    if bool(ind_fig.data):
        chart_cards_html += _plot_card_markup(
            plot_id="single-indicator-chart",
            title=indicator_title,
        )
        chart_scripts.append(_plot_script("single-indicator-chart", ind_fig))

    if bool(score_fig.data):
        chart_cards_html += _plot_card_markup(
            plot_id="single-score-chart",
            title=_t(language, tr("factor.score"), "Factor score"),
        )
        chart_scripts.append(_plot_script("single-score-chart", score_fig))

    if bool(equity_fig.data):
        chart_cards_html += _plot_card_markup(
            plot_id="single-equity-chart",
            title=_t(language, tr("backtest.net_value_drawdown"), "Backtest equity / drawdown"),
            wide=True, tall=True,
        )
        chart_scripts.append(_plot_script("single-equity-chart", equity_fig))

    if bool(signal_fig.data):
        chart_cards_html += _plot_card_markup(
            plot_id="single-signal-chart",
            title=_t(language, tr("testSet.tradingSignals"), "Test-set trade signals"),
            wide=True,
        )
        chart_scripts.append(_plot_script("single-signal-chart", signal_fig))

    if chart_cards_html:
        html_parts.append(f"""
    <section class="section-stack">
      <article class="paper-block">
        <div class="section-kicker">{_esc(_t(language, "图表", "Charts"))}</div>
        <h2 class="section-title">{_esc(_t(language, tr("ui.chart_result_area"), "Chart result surface"))}</h2>
      </article>
      <div class="chart-grid">
        {chart_cards_html}
      </div>
    </section>
""")
        html_parts.extend(chart_scripts)

    html_parts.append(_build_footer(language))
    return "".join(html_parts)


def _build_portfolio_stock_analysis_html(portfolio_result: dict, language: str) -> str:
    """Generate per-stock strategy analysis for multi-stock portfolio."""
    if not portfolio_result:
        return ""

    individual = portfolio_result.get("individual_results") or {}
    weights = portfolio_result.get("weights") or {}
    if len(individual) < 2:
        return ""

    # Compute averages
    returns = [r.get("total_return", 0) for r in individual.values()]
    sharpes = [r.get("sharpe", 0) for r in individual.values()]
    avg_ret = sum(returns) / len(returns) if returns else 0
    avg_sharpe = sum(sharpes) / len(sharpes) if sharpes else 0

    cards: list[str] = []
    for sym, res in individual.items():
        ret = res.get("total_return", 0)
        sharpe = res.get("sharpe", 0)
        maxdd = res.get("max_dd", 0)
        weight = weights.get(sym, 0)

        insights: list[str] = []
        tone = "neutral"

        if ret > avg_ret * 1.2:
            insights.append(_t(language,
                f"收益率 ({ret:.1%}) 显著高于组合平均 ({avg_ret:.1%})，是组合收益的主要贡献者",
                f"Return ({ret:.1%}) significantly above portfolio average ({avg_ret:.1%}), major contributor to portfolio gains"))
            tone = "positive"
        elif ret < avg_ret * 0.5 or ret < 0:
            insights.append(_t(language,
                f"收益率 ({ret:.1%}) 明显低于组合平均 ({avg_ret:.1%})，拖累组合表现",
                f"Return ({ret:.1%}) well below portfolio average ({avg_ret:.1%}), drags portfolio performance"))
            tone = "negative"

        if sharpe > avg_sharpe * 1.2:
            insights.append(_t(language,
                f"夏普比率 ({sharpe:.2f}) 优于组合平均 ({avg_sharpe:.2f})，风险调整后回报出色",
                f"Sharpe ({sharpe:.2f}) above portfolio average ({avg_sharpe:.2f}), strong risk-adjusted returns"))
        elif sharpe < 0:
            insights.append(_t(language,
                f"夏普比率为负 ({sharpe:.2f})，该标的策略在样本期内亏损",
                f"Negative Sharpe ({sharpe:.2f}), strategy lost money in sample period"))
            tone = "negative"

        if abs(maxdd) > 0.3:
            insights.append(_t(language,
                f"最大回撤较深 ({maxdd:.1%})，需要关注极端行情下的风险暴露",
                f"Deep max drawdown ({maxdd:.1%}), monitor risk exposure in extreme conditions"))
        elif abs(maxdd) < 0.1:
            insights.append(_t(language,
                f"回撤控制良好 ({maxdd:.1%})，波动较小",
                f"Good drawdown control ({maxdd:.1%}), low volatility"))

        if not insights:
            insights.append(_t(language, "表现接近组合平均水平", "Performance close to portfolio average"))

        tone_class = {"positive": "insight-positive", "negative": "insight-negative"}.get(tone, "insight-neutral")
        insight_html = "".join(f"<li>{_esc(ins)}</li>" for ins in insights)

        cards.append(f"""
        <div class="stock-insight-card {tone_class}">
          <div class="stock-insight-header">
            <strong>{_esc(sym)}</strong>
            <span class="stock-weight-badge">{_t(language, '权重', 'Weight')} {weight:.1%}</span>
          </div>
          <ul class="stock-insight-list">{insight_html}</ul>
          <div class="stock-insight-metrics">
            <span>{_t(language, '收益', 'Return')} {ret:.2%}</span>
            <span>{_t(language, '夏普', 'Sharpe')} {sharpe:.2f}</span>
            <span>{_t(language, '回撤', 'DD')} {maxdd:.2%}</span>
          </div>
        </div>""")

    return "".join(cards)


def _build_portfolio_stock_analysis_section(portfolio_result: dict, language: str) -> str:
    """Wrap per-stock analysis cards in a titled section block."""
    stock_analysis_html = _build_portfolio_stock_analysis_html(portfolio_result, language)
    if not stock_analysis_html:
        return ""
    return f"""
      <article class="paper-block">
        <div class="section-kicker" style="margin-top:1.5rem">{_esc(_t(language, "个股分析", "Per-Stock Analysis"))}</div>
        <h3 style="margin:0.5rem 0 1rem">{_esc(_t(language, "各标的策略表现解读", "Individual Stock Strategy Performance Analysis"))}</h3>
        <p class="section-copy">{_esc(_t(language, "基于各标的在组合策略中的回测表现，自动分析其对组合的贡献与风险。", "Automated analysis of each stock's contribution and risk based on portfolio backtest performance."))}</p>
        <div class="model-analysis-grid">
          {stock_analysis_html}
        </div>
      </article>"""


def build_multi_stock_export_html(
    *,
    title: str,
    compare_stocks: list[str],
    stock_data_dict: dict[str, pd.DataFrame],
    comparison_stats: list[dict[str, Any]],
    comparison_fig: go.Figure | None,
    rs_fig: go.Figure | None,
    risk_return_fig: go.Figure | None,
    factor_score_fig: go.Figure | None,
    corr_fig: go.Figure | None,
    periodic_heatmap_fig: go.Figure | None,
    portfolio_result: dict[str, Any] | None,
    include_date: bool,
    market: str = "",
    language: str = "zh",
    theme: str = "light",
    generated_at: datetime | None = None,
) -> str:
    language = _lang(language)
    theme = _theme(theme)
    total_stocks = len(stock_data_dict)
    avg_days = int(sum(item.get("data_days", 0) for item in comparison_stats) / total_stocks) if total_stocks and comparison_stats else 0
    best_entry = next((item for item in comparison_stats if item.get("total_return") is not None), None)
    best_symbol = best_entry.get("symbol") if best_entry is not None else "N/A"
    best_return = best_entry.get("total_return") if best_entry is not None else None

    cards = [
        {"label": _t(language, tr("comparison.stockCount"), "Compared symbols"), "value": str(total_stocks), "meta": _t(language, tr("export.valid_stocks_count"), "Effective symbols included in this export")},
        {"label": _t(language, tr("data.averageDays"), "Average data days"), "value": str(avg_days), "meta": _t(language, tr("filter.validSamples.currentTime"), "Effective samples after the current date filter")},
        {"label": _t(language, tr("performance.best"), "Best performer"), "value": best_symbol, "meta": _t(language, f"区间收益 {_fmt_pct(best_return, signed=True)}", f"Range return {_fmt_pct(best_return, signed=True)}")},
        {"label": _t(language, tr("results.portfolio"), "Portfolio result"), "value": _t(language, tr("state.generated") if portfolio_result else tr("status.notGenerated"), "Ready" if portfolio_result else "Not generated"), "meta": _t(language, tr("strategy.generation.includes"), "Includes KPIs and stock contribution table when available")},
    ]
    overview_items = [
        {"label": _t(language, tr("stock.pool"), "Stock pool"), "value": ", ".join(compare_stocks) if compare_stocks else "N/A", "meta": _t(language, tr("export.preserveStockOrder"), "The export keeps the current stock-pool order from the main page")},
        {"label": _t(language, tr("performance.topPerformer"), "Best performing stock"), "value": best_symbol, "meta": _t(language, f"区间收益 {_fmt_pct(best_return, signed=True)}", f"Range return {_fmt_pct(best_return, signed=True)}")},
        {"label": _t(language, tr("component.basicInfo.structure"), "Basics structure"), "value": _t(language, tr("report.composition"), "Summary metrics + detail table + chart group"), "meta": _t(language, tr("requirement.align_chart_four"), "Aligned with Figure 4")},
        {"label": _t(language, tr("strategy.resultStructure"), "Strategy structure"), "value": _t(language, tr("dashboard.combinedLayout"), "Portfolio KPIs + stock table + main chart"), "meta": _t(language, tr("chart.alignmentRequirement"), "Aligned with Figure 5")},
    ]
    comparison_rows = [[
        _esc(str(item.get("symbol") or "N/A")),
        _esc(str(item.get("display_name") or "N/A")),
        _esc(_fmt_decimal(item.get("start_price"))),
        _esc(_fmt_decimal(item.get("latest_price"))),
        _esc(_fmt_pct(item.get("total_return"), signed=True)),
        _esc(_fmt_pct(item.get("annualized_return"), signed=True)),
        _esc(_fmt_decimal(item.get("high_price"))),
        _esc(_fmt_decimal(item.get("low_price"))),
        _esc(str(item.get("data_days") or 0)),
    ] for item in comparison_stats]

    strategy_rows: list[list[str]] = []
    if portfolio_result:
        weights = dict(portfolio_result.get("weights") or {})
        for symbol, result in (portfolio_result.get("individual_results") or {}).items():
            strategy_rows.append([
                _esc(symbol),
                _esc(_fmt_pct(weights.get(symbol), digits=1)),
                _esc(_fmt_pct(result.get("total_return"), signed=True)),
                _esc(_fmt_ratio(result.get("sharpe"))),
                _esc(_fmt_pct(result.get("max_dd"), signed=True)),
            ])

    chips = [_t(language, tr("export.multiStockReport"), "Multi-stock export report"), _t(language, tr("layout.site_sync"), "Site-structure synced"), _t(language, f"{total_stocks} 个标的", f"{total_stocks} symbols"), _t(language, tr("report.offlineHtml"), "Offline HTML")]
    if include_date:
        chips.append(f"{_t(language, tr("meta.generatedTime"), 'Generated at')} {_fmt_generated_at(generated_at, language)}")

    html_parts = [_build_head(title, theme, language)]
    html_parts.append(
        f"""
    <section class="export-hero">
      <div class="hero-kicker">{_esc(_t(language, "Strategy Lab Report", "Strategy Lab Report"))}</div>
      <h1 class="hero-title">{_esc(title)}</h1>
      <p class="hero-copy">{_esc(_t(language, tr("export.page.description"), "The export gathers multi-stock basics, cross-sectional comparison, and portfolio strategy results into one site-style report instead of returning to the old stacked-card layout."))}</p>
      <div class="chip-row">{"".join(f"<span class='chip{' accent' if index == 0 else ''}'>{_esc(chip)}</span>" for index, chip in enumerate(chips))}</div>
      <div class="stat-grid">{_build_stat_cards(cards)}</div>
    </section>
    <section class="report-grid">
      <article class="paper-block">
        <div class="section-kicker">{_esc(_t(language, "Overview", "Overview"))}</div>
        <h2 class="section-title">{_esc(_t(language, tr("multiStock.overview"), "Multi-stock overview"))}</h2>
        <p class="section-copy">{_esc(_t(language, tr("analysis.flow.summaryFirst"), "Start with summary metrics that explain pool size, sample window, and result structure before moving into tables and charts."))}</p>
        <div class="kv-grid">{_build_kv_items(overview_items)}</div>
      </article>
      <article class="paper-block">
        <div class="section-kicker">{_esc(_t(language, "Figure 4", "Figure 4"))}</div>
        <h2 class="section-title">{_esc(_t(language, tr("table.detailedComparison"), "Detailed comparison table"))}</h2>
        <p class="section-copy">{_esc(_t(language, tr("summaryTable.description"), "This table carries the Figure 4 requirement of “summary metrics + detail table” so that not all information is forced into charts."))}</p>
        {_build_table([_t(language, tr("field.symbol"), "Ticker"), _t(language, tr("common.name"), "Name"), _t(language, tr("metric.startPrice"), "Start price"), _t(language, tr("price.latest"), "Latest price"), _t(language, tr("metric.totalReturn"), "Total return"), _t(language, tr("metrics.annualizedReturn"), "Annualized return"), _t(language, tr("price.highest"), "High"), _t(language, tr("price.low"), "Low"), _t(language, tr("data.days"), "Data days")], comparison_rows)}
      </article>
    </section>
    <section class="section-stack">
      <article class="paper-block">
        <div class="section-kicker">{_esc(_t(language, "Charts", "Charts"))}</div>
        <h2 class="section-title">{_esc(_t(language, tr("chart.multiStock.basicInfo"), "Multi-stock basics charts"))}</h2>
        <p class="section-copy">{_esc(_t(language, tr("layout.mainChartArea.function"), "The right-side chart surface keeps price comparison, relative strength, risk-return, factor score, and correlation together instead of turning into a long stacked page."))}</p>
      </article>
      <div class="chart-grid">
        {(_plot_card_markup(plot_id="multi-comparison-chart", title=_t(language, tr("chart.price_comparison"), "Price comparison"), copy=_t(language, tr("comparison.unified_start"), "All symbols are rebased to the same starting level so relative speed is visible first."), wide=True, tall=True) if comparison_fig is not None else "")}
        {(_plot_card_markup(plot_id="multi-rs-chart", title=_t(language, tr("chart.relativeStrength"), "Relative strength"), copy=_t(language, tr("description.baseline_equal_weight"), "The equal-weight basket stays as the default benchmark to show who consistently leads or lags the pool.")) if rs_fig is not None else "")}
        {(_plot_card_markup(plot_id="multi-risk-return-chart", title=_t(language, tr("analysis.riskReturn"), "Risk-return analysis"), copy=_t(language, tr("analysis.riskReturnSharpeDescription"), "Return, risk, and Sharpe are kept in one plane to surface structural differences quickly.")) if risk_return_fig is not None else "")}
        {(_plot_card_markup(plot_id="multi-factor-score-chart", title=_t(language, tr("factor.latestScoreComparison"), "Latest factor score"), copy=_t(language, tr("analysis.secondary_judgment_line"), "It answers who deserves attention now and acts as a second reading line beyond price charts.")) if factor_score_fig is not None else "")}
        {(_plot_card_markup(plot_id="multi-corr-chart", title=_t(language, tr("analysis.correlationHeatmap"), "Correlation heatmap"), copy=_t(language, tr("analysis.identify_homogeneity"), "Helps reveal whether the stock pool is overly homogeneous.")) if corr_fig is not None else "")}
      </div>
    </section>
"""
    )
    if comparison_fig is not None:
        html_parts.append(_plot_script("multi-comparison-chart", comparison_fig))
    if rs_fig is not None:
        html_parts.append(_plot_script("multi-rs-chart", rs_fig))
    if risk_return_fig is not None:
        html_parts.append(_plot_script("multi-risk-return-chart", risk_return_fig))
    if factor_score_fig is not None:
        html_parts.append(_plot_script("multi-factor-score-chart", factor_score_fig))
    if corr_fig is not None:
        html_parts.append(_plot_script("multi-corr-chart", corr_fig))

    # ── Stock pool summary ────────────────────────────────────────────────────
    market_display = {"US": "US Stock (NYSE/NASDAQ)", "CN_A": "A-Share (SSE/SZSE)"}.get(market, market or "N/A")
    pool_profile_items = [
        {"label": _t(language, "市场", "Market"), "value": market_display, "meta": ""},
        {"label": _t(language, "标的数量", "Symbol Count"), "value": str(total_stocks), "meta": _t(language, f"平均 {avg_days} 个交易日", f"Average {avg_days} trading days")},
        {"label": _t(language, "最佳表现", "Top Performer"), "value": best_symbol, "meta": _fmt_pct(best_return, signed=True)},
    ]
    html_parts.append(f"""
    <section class="section-stack">
      <article class="paper-block">
        <div class="section-kicker">{_esc(_t(language, "Stock Pool", "Stock Pool"))}</div>
        <h2 class="section-title">{_esc(_t(language, "标的池概览", "Stock Pool Overview"))}</h2>
        <div class="kv-grid">{_build_kv_items(pool_profile_items)}</div>
      </article>
    </section>
""")

    if portfolio_result:
        portfolio_cards = [
            {"label": _t(language, tr("portfolio.totalReturn"), "Portfolio return"), "value": _fmt_pct(portfolio_result.get("port_total_return"), signed=True), "meta": _t(language, f"夏普 {_fmt_ratio(portfolio_result.get('port_sharpe'))}", f"Sharpe {_fmt_ratio(portfolio_result.get('port_sharpe'))}")},
            {"label": _t(language, tr("metric.portfolio_max_drawdown"), "Portfolio max drawdown"), "value": _fmt_pct(portfolio_result.get("port_max_dd"), signed=True), "meta": _t(language, tr("nav.strategy_portfolio"), "Strategy portfolio")},
            {"label": _t(language, tr("metric.buyAndHoldReturn"), "Buy-and-hold return"), "value": _fmt_pct(portfolio_result.get("bh_total_return"), signed=True), "meta": _t(language, f"夏普 {_fmt_ratio(portfolio_result.get('bh_sharpe'))}", f"Sharpe {_fmt_ratio(portfolio_result.get('bh_sharpe'))}")},
            {"label": _t(language, tr("metrics.buy_hold_drawdown"), "Buy-and-hold drawdown"), "value": _fmt_pct(portfolio_result.get("bh_max_dd"), signed=True), "meta": _t(language, tr("benchmark.equalWeight"), "Equal-weight benchmark")},
        ]
        html_parts.append(
            f"""
    <section class="section-stack">
      <article class="paper-block">
        <div class="section-kicker">{_esc(_t(language, "Figure 5", "Figure 5"))}</div>
        <h2 class="section-title">{_esc(_t(language, tr("strategy.multiStockResults"), "Multi-stock strategy result"))}</h2>
        <p class="section-copy">{_esc(_t(language, tr("results.stableZone"), "This section keeps portfolio KPIs, the main result chart, and the stock performance table together so stable information does not get scattered when the main chart changes."))}</p>
        <div class="stat-grid">{_build_stat_cards(portfolio_cards)}</div>
        {_build_table([_t(language, tr("instrument.type.stock"), "Stock"), _t(language, tr("common.weight"), "Weight"), _t(language, tr("metric.strategyReturn"), "Strategy return"), _t(language, tr("metric.sharpe_ratio"), "Sharpe ratio"), _t(language, tr("metrics.max_drawdown"), "Max drawdown")], strategy_rows or [[_esc(_t(language, tr("common.noData"), "N/A")), "N/A", "N/A", "N/A", "N/A"]])}
      </article>
      {_build_portfolio_stock_analysis_section(portfolio_result, language)}
      <div class="chart-grid">
        {_plot_card_markup(plot_id="multi-portfolio-chart", title=_t(language, tr("simulation.portfolio"), "Portfolio simulation"), copy=_t(language, tr("chart.reusePortfolioChart"), "The main chart continues to reuse the portfolio equity view from the result board."), wide=True, tall=True)}
        {(_plot_card_markup(plot_id="multi-periodic-heatmap-chart", title=_t(language, tr("chart.periodReturnHeatmap"), "Periodic return heatmap"), copy=_t(language, tr("chart.periodHeatmapLayout"), "The periodic heatmap is separated from the main chart so both desktop and mobile remain readable."), wide=True) if periodic_heatmap_fig is not None else "")}
      </div>
    </section>
"""
        )
        if portfolio_result.get("fig") is not None:
            html_parts.append(_plot_script("multi-portfolio-chart", portfolio_result["fig"]))
        if periodic_heatmap_fig is not None:
            html_parts.append(_plot_script("multi-periodic-heatmap-chart", periodic_heatmap_fig))

    html_parts.append(_build_footer(language))
    return "".join(html_parts)
