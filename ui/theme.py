"""
共享前端主题层
==============
为 W6 首页、入口页和路由壳层提供暖米白官网式样式。
"""

from __future__ import annotations

import html
import re
from datetime import date as _date, datetime as _datetime
from functools import lru_cache, wraps
from textwrap import dedent
from urllib.parse import urlencode

import streamlit as st
from ui.i18n import get_ui_language as _get_i18n_language
from ui.i18n import tr


BASE_ROUTE_PATH = "/strategy"
UI_LANGUAGE_STATE_KEY = "ui_language"
UI_THEME_STATE_KEY = "ui_theme"



def ensure_ui_preferences() -> None:
    st.session_state[UI_LANGUAGE_STATE_KEY] = _get_i18n_language()
    st.session_state.setdefault(UI_THEME_STATE_KEY, "light")


def get_ui_language() -> str:
    return _get_i18n_language()


def get_ui_theme() -> str:
    ensure_ui_preferences()
    theme = str(st.session_state.get(UI_THEME_STATE_KEY, "light")).strip().lower()
    return "dark" if theme == "dark" else "light"


def translate_text(value: object) -> object:
    if not isinstance(value, str) or get_ui_language() != "en":
        return value

    from ui.i18n import LOCALES
    if not hasattr(translate_text, "_cached_pairs"):
        pairs = []
        for k, v in LOCALES.items():
            zh = v.get('zh', '').strip()
            en = v.get('en', '').strip()
            if zh and zh != en:
                pairs.append((zh, en))
        translate_text._cached_pairs = sorted(pairs, key=lambda x: len(x[0]), reverse=True)

    translated = value
    for source, target in translate_text._cached_pairs:
        if source in translated:
            translated = translated.replace(source, target)
    return translated


def t(zh: str, en: str) -> str:
    return en if get_ui_language() == "en" else zh


def _get_ui_theme_style_values() -> dict[str, str]:
    if get_ui_theme() == "dark":
        return {
            "root_tokens": """
  --bg-canvas: #151210;
  --bg-canvas-strong: #211b17;
  --bg-glow: rgba(224, 161, 108, 0.16);
  --bg-glow-soft: rgba(84, 64, 44, 0.34);

  --surface-main: rgba(41, 33, 28, 0.9);
  --surface-sheet: rgba(45, 36, 30, 0.96);
  --surface-frost: rgba(53, 42, 35, 0.84);
  --surface-soft: rgba(61, 47, 39, 0.9);
  --surface-line: rgba(242, 231, 217, 0.12);
  --surface-line-strong: rgba(242, 231, 217, 0.2);

  --text-strong: #fff4e7;
  --text-primary: #f2e7d9;
  --text-secondary: #d6bea5;
  --text-muted: #bba286;
  --text-inverse: #18130f;

  --accent-primary: #fff4e7;
  --accent-primary-soft: rgba(255, 244, 231, 0.09);
  --accent-warm: #e0a16c;
  --accent-positive: #7ec28d;
  --accent-warning: #f0b469;
  --accent-danger: #ff8d86;
  --market-pulse-line: #e0a16c;
  --market-pulse-highlight: #fff4e7;
  --market-pulse-positive: #7ec28d;

  --shadow-soft: 0 28px 68px rgba(0, 0, 0, 0.34);
  --shadow-board: 0 36px 92px rgba(0, 0, 0, 0.38);
            """.strip(),
            "app_background": """
  background:
    radial-gradient(circle at 14% 10%, var(--bg-glow), transparent 24%),
    radial-gradient(circle at 86% 9%, var(--bg-glow-soft), transparent 25%),
    radial-gradient(circle at 52% 18%, rgba(77, 58, 42, 0.18), transparent 28%),
    linear-gradient(180deg, var(--bg-canvas-strong) 0%, var(--bg-canvas) 100%);
            """.strip(),
            "sidebar_background": "rgba(31, 25, 21, 0.96)",
            "active_tab_shadow": "0 10px 28px rgba(0, 0, 0, 0.25)",
        }

    return {
        "root_tokens": """
  --bg-canvas: #f7efe2;
  --bg-canvas-strong: #f1e3cf;
  --bg-glow: rgba(222, 184, 133, 0.24);
  --bg-glow-soft: rgba(244, 232, 210, 0.56);

  --surface-main: rgba(255, 250, 243, 0.84);
  --surface-sheet: rgba(255, 249, 241, 0.96);
  --surface-frost: rgba(255, 247, 236, 0.8);
  --surface-soft: rgba(245, 233, 213, 0.88);
  --surface-line: rgba(123, 95, 64, 0.12);
  --surface-line-strong: rgba(123, 95, 64, 0.22);

  --text-strong: #18130f;
  --text-primary: #473626;
  --text-secondary: #765d45;
  --text-muted: #9a8268;
  --text-inverse: #fffdf8;

  --accent-primary: #1f1914;
  --accent-primary-soft: rgba(31, 25, 20, 0.08);
  --accent-warm: #ba7349;
  --accent-positive: #4e7c59;
  --accent-warning: #a46429;
  --accent-danger: #b34a45;
  --market-pulse-line: #a65e34;
  --market-pulse-highlight: #2d2018;
  --market-pulse-positive: #4e7c59;

  --shadow-soft: 0 24px 56px rgba(78, 54, 29, 0.08);
  --shadow-board: 0 34px 78px rgba(78, 54, 29, 0.1);
        """.strip(),
        "app_background": """
  background:
    radial-gradient(circle at 14% 10%, var(--bg-glow), transparent 24%),
    radial-gradient(circle at 86% 9%, var(--bg-glow-soft), transparent 25%),
    radial-gradient(circle at 52% 18%, rgba(255, 251, 245, 0.86), transparent 28%),
    linear-gradient(180deg, #fbf6ee 0%, var(--bg-canvas) 100%);
        """.strip(),
        "sidebar_background": "rgba(252, 248, 241, 0.96)",
        "active_tab_shadow": "0 8px 24px rgba(78, 54, 29, 0.12)",
    }


def get_plotly_theme_tokens() -> dict[str, object]:
    if get_ui_theme() == "dark":
        return {
            "font_family": '"Avenir Next","Segoe UI","PingFang SC","Microsoft YaHei",sans-serif',
            "font_color": "#f2e7d9",
            "muted_text": "#c5ab90",
            "paper_bg": "rgba(21, 18, 16, 0.96)",
            "paper_bg_transparent": "rgba(21, 18, 16, 0.0)",
            "plot_bg": "rgba(34, 28, 24, 0.94)",
            "grid": "rgba(242, 231, 217, 0.12)",
            "axis_line": "rgba(242, 231, 217, 0.18)",
            "legend_bg": "rgba(47, 39, 33, 0.92)",
            "annotation_bg": "rgba(47, 39, 33, 0.96)",
            "annotation_border": "rgba(242, 231, 217, 0.14)",
            "accent_warm": "#e0a16c",
            "accent_primary": "#fff3e3",
            "accent_positive": "#7ec28d",
            "accent_danger": "#ff8d86",
            "market_up": "#ff8d86",
            "market_down": "#7ec28d",
            "color_sequence": ["#e0a16c", "#7ec28d", "#8fb4ff", "#ff8d86", "#c9a6ff", "#8ed3d1", "#f2c37a"],
        }

    return {
        "font_family": '"Avenir Next","Segoe UI","PingFang SC","Microsoft YaHei",sans-serif',
        "font_color": "#473626",
        "muted_text": "#765d45",
        "paper_bg": "rgba(255, 252, 247, 0.94)",
        "paper_bg_transparent": "rgba(255, 252, 247, 0.0)",
        "plot_bg": "rgba(255, 252, 247, 0.94)",
        "grid": "rgba(123, 95, 64, 0.10)",
        "axis_line": "rgba(123, 95, 64, 0.14)",
        "legend_bg": "rgba(255, 249, 241, 0.92)",
        "annotation_bg": "rgba(255, 249, 241, 0.92)",
        "annotation_border": "rgba(123, 95, 64, 0.12)",
        "accent_warm": "#ba7349",
        "accent_primary": "#1f1914",
        "accent_positive": "#4e7c59",
        "accent_danger": "#b34a45",
        "market_up": "#b34a45",
        "market_down": "#4e7c59",
        "color_sequence": ["#ba7349", "#4e7c59", "#496a9f", "#b34a45", "#8a67aa", "#58939a", "#d29b52"],
    }


def apply_plotly_theme(
    fig,
    *,
    height: int | None = None,
    margin: dict[str, int] | None = None,
    transparent_paper: bool = False,
    hovermode: str | None = None,
):
    if fig is None:
        return None

    tokens = get_plotly_theme_tokens()
    legend_update = dict(
        bgcolor=tokens["legend_bg"],
        bordercolor=tokens["axis_line"],
        borderwidth=1,
        font=dict(color=tokens["font_color"]),
        title=dict(font=dict(color=tokens["font_color"])),
    )
    fig.update_layout(
        template="none",
        height=height or getattr(fig.layout, "height", None),
        margin=margin or getattr(fig.layout, "margin", None),
        paper_bgcolor=tokens["paper_bg_transparent"] if transparent_paper else tokens["paper_bg"],
        plot_bgcolor=tokens["plot_bg"],
        font=dict(family=tokens["font_family"], color=tokens["font_color"]),
        colorway=list(tokens["color_sequence"]),
        legend=legend_update,
    )
    if hovermode is not None:
        fig.update_layout(hovermode=hovermode)

    fig.update_xaxes(
        gridcolor=tokens["grid"],
        linecolor=tokens["axis_line"],
        zerolinecolor=tokens["axis_line"],
        tickfont=dict(color=tokens["font_color"]),
        title_font=dict(color=tokens["font_color"]),
    )
    fig.update_yaxes(
        gridcolor=tokens["grid"],
        linecolor=tokens["axis_line"],
        zerolinecolor=tokens["axis_line"],
        tickfont=dict(color=tokens["font_color"]),
        title_font=dict(color=tokens["font_color"]),
    )

    figure_title = getattr(fig.layout, "title", None)
    figure_title_text = getattr(figure_title, "text", None)
    if isinstance(figure_title_text, str) and figure_title_text.strip():
        fig.layout.title.text = translate_text(figure_title_text)
        fig.layout.title.font = {
            **(fig.layout.title.font.to_plotly_json() if fig.layout.title.font else {}),
            "color": tokens["font_color"],
            "family": tokens["font_family"],
        }

    legend_title = getattr(getattr(fig.layout, "legend", None), "title", None)
    legend_title_text = getattr(legend_title, "text", None)
    if isinstance(legend_title_text, str) and legend_title_text.strip():
        fig.layout.legend.title.text = translate_text(legend_title_text)

    for axis_name in [key for key in fig.layout if str(key).startswith(("xaxis", "yaxis"))]:
        axis = fig.layout[axis_name]
        if getattr(axis, "title", None) is not None and getattr(axis.title, "text", None):
            axis.title.text = translate_text(axis.title.text)
        if getattr(axis, "rangeselector", None) is not None and getattr(axis.rangeselector, "buttons", None):
            for button in axis.rangeselector.buttons:
                if getattr(button, "label", None):
                    button.label = translate_text(button.label)

    for annotation in list(getattr(fig.layout, "annotations", []) or []):
        annotation.text = translate_text(annotation.text)
        if annotation.font is None:
            annotation.font = {}
        annotation.font.color = tokens["font_color"]
        annotation.font.family = tokens["font_family"]
        if getattr(annotation, "bgcolor", None):
            annotation.bgcolor = tokens["annotation_bg"]
        if getattr(annotation, "bordercolor", None):
            annotation.bordercolor = tokens["annotation_border"]

    for trace in list(getattr(fig, "data", []) or []):
        if getattr(trace, "name", None):
            trace.name = translate_text(trace.name)
        if getattr(trace, "hovertemplate", None):
            trace.hovertemplate = translate_text(trace.hovertemplate)
        trace_text = getattr(trace, "text", None)
        if isinstance(trace_text, str):
            trace.text = translate_text(trace_text)
        if getattr(trace, "textfont", None) is not None and hasattr(trace.textfont, "color"):
            trace.textfont.color = tokens["font_color"]
        if getattr(trace, "colorbar", None) is not None and getattr(trace.colorbar, "title", None) is not None:
            trace.colorbar.title.text = translate_text(trace.colorbar.title.text)
            trace.colorbar.title.font = {
                **(trace.colorbar.title.font.to_plotly_json() if trace.colorbar.title.font else {}),
                "color": tokens["font_color"],
            }
    return fig


def _wrap_streamlit_text_method(func_name: str) -> None:
    original = getattr(st, func_name)

    @wraps(original)
    def wrapper(*args, **kwargs):
        if func_name == "tabs" and args and isinstance(args[0], (list, tuple)):
            localized_labels = [
                translate_text(label) if isinstance(label, str) else label
                for label in args[0]
            ]
            args = (localized_labels, *args[1:])
        else:
            args = tuple(translate_text(arg) if isinstance(arg, str) else arg for arg in args)
        for key in ("help", "placeholder"):
            if isinstance(kwargs.get(key), str):
                kwargs[key] = translate_text(kwargs[key])
        if func_name in {"selectbox", "radio", "segmented_control", "multiselect"}:
            if callable(kwargs.get("format_func")):
                base_format = kwargs["format_func"]

                @wraps(base_format)
                def localized_format(value):
                    result = base_format(value)
                    return translate_text(result) if isinstance(result, str) else result

                kwargs["format_func"] = localized_format
            else:
                kwargs["format_func"] = lambda value: translate_text(value) if isinstance(value, str) else value
        return original(*args, **kwargs)

    setattr(st, func_name, wrapper)


def _wrap_streamlit_write() -> None:
    original = st.write

    @wraps(original)
    def wrapper(*args, **kwargs):
        localized_args = tuple(translate_text(arg) if isinstance(arg, str) else arg for arg in args)
        return original(*localized_args, **kwargs)

    st.write = wrapper


def install_streamlit_localizers() -> None:
    if getattr(st, "_strategy_i18n_patched", False):
        return

    for method_name in [
        "markdown",
        "caption",
        "button",
        "checkbox",
        "toggle",
        "text_input",
        "text_area",
        "date_input",
        "multiselect",
        "selectbox",
        "radio",
        "segmented_control",
        "file_uploader",
        "slider",
        "number_input",
        "subheader",
        "header",
        "title",
        "info",
        "warning",
        "error",
        "success",
        "spinner",
        "popover",
        "expander",
        "metric",
        "tabs",
        "form_submit_button",
        "download_button",
    ]:
        if hasattr(st, method_name):
            _wrap_streamlit_text_method(method_name)
    _wrap_streamlit_write()
    st._strategy_i18n_patched = True


def route_href(
    url_path: str = "",
    *,
    language: str | None = None,
    query: dict[str, str] | None = None,
) -> str:
    """system.routing.buildPath"""
    normalized = str(url_path or "").strip().strip("/")
    base = f"{BASE_ROUTE_PATH}/{normalized}" if normalized else BASE_ROUTE_PATH
    active_language = str(language or get_ui_language()).strip().lower()
    active_language = "zh" if active_language.startswith("zh") else "en"
    parameters = {"lang": active_language, **(query or {})}
    return f"{base}?{urlencode(parameters)}"

def render_html(markup: str, *, localize: bool = True) -> None:
    """ui.renderMultiLineHTML"""
    body = dedent(markup).strip()
    if localize:
        body = str(translate_text(body))
    if hasattr(st, "html"):
        st.html(body)
        return
    st.markdown(body, unsafe_allow_html=True)


def _coerce_date_value(value: object) -> _date | None:
    if value is None:
        return None
    if isinstance(value, _datetime):
        return value.date()
    if isinstance(value, _date):
        return value
    try:
        timestamp = _datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return timestamp.date()


def _normalize_date_range(value: object) -> tuple[_date, ...]:
    if isinstance(value, (list, tuple)):
        normalized = tuple(
            normalized_item
            for normalized_item in (_coerce_date_value(item) for item in value)
            if normalized_item is not None
        )
        return normalized[:2]

    single_value = _coerce_date_value(value)
    return (single_value,) if single_value is not None else ()


def render_analysis_date_range_control(
    *,
    current_range: object,
    key_prefix: str,
    label: str = tr("time.range"),
    in_hero: bool = False,
) -> None:
    """ui.render_time_range_control"""
    normalized_current = _normalize_date_range(
        st.session_state.get("sidebar_selected_range", current_range)
    )
    if not normalized_current:
        today = _date.today()
        normalized_current = (today.replace(year=max(2015, today.year - 3)), today)

    widget_key = f"{key_prefix}_header_selected_range"
    if _normalize_date_range(st.session_state.get(widget_key)) != normalized_current:
        st.session_state[widget_key] = normalized_current

    host_key = f"{key_prefix}-header-range"
    with st.container(key=host_key):
        if in_hero:
            st.caption(label)
            selected = st.date_input(
                label,
                value=normalized_current,
                min_value=_date(2015, 1, 1),
                max_value=_date.today(),
                key=widget_key,
                label_visibility="collapsed",
            )
        else:
            control_col, _spacer_col = st.columns([0.78, 1.22], gap="large")
            with control_col:
                st.caption(label)
                selected = st.date_input(
                    label,
                    value=normalized_current,
                    min_value=_date(2015, 1, 1),
                    max_value=_date.today(),
                    key=widget_key,
                    label_visibility="collapsed",
                )

    selected_normalized = _normalize_date_range(selected)
    if selected_normalized and selected_normalized != normalized_current:
        st.session_state["sidebar_selected_range"] = selected_normalized
        st.rerun()


def _build_style_source() -> str:
    """Build the complete CSS source before it is partitioned by route."""
    theme_styles = _get_ui_theme_style_values()
    style_markup = """
:root {
__ROOT_TOKENS__
}

html,
body,
[class*="css"] {
  font-family: "Avenir Next", "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
}

body {
  color: var(--text-primary);
}

.stApp {
__APP_BACKGROUND__
  color: var(--text-primary);
}

a,
a:hover,
a:visited,
a:active {
  text-decoration: none !important;
}

[data-testid="stHeader"] {
  display: none;
}

#MainMenu,
footer {
  visibility: hidden;
}

[data-testid="stSidebar"] {
  background: __SIDEBAR_BACKGROUND__;
  border-right: 1px solid var(--surface-line);
}

.block-container {
  max-width: 1480px;
  padding-top: 0.7rem;
  padding-bottom: 4rem;
}

[data-baseweb="tab-list"] {
  background: var(--surface-frost);
  border: 1px solid var(--surface-line);
  border-radius: 999px;
  padding: 0.2rem;
  gap: 0.12rem;
}

[data-baseweb="tab"] {
  color: var(--text-secondary);
  border-radius: 999px;
  min-height: 38px;
}

[data-baseweb="tab"][aria-selected="true"] {
  background: var(--surface-sheet);
  color: var(--text-strong);
  box-shadow: __ACTIVE_TAB_SHADOW__;
}

.site-header {
  display: grid;
  grid-template-columns: minmax(180px, 1fr) auto minmax(180px, 1fr);
  align-items: center;
  gap: clamp(1rem, 2.8vw, 3rem);
  width: 100%;
  min-height: 4.2rem;
  margin: 0 auto;
  padding: 0.2rem 0 0.65rem;
}

div[class*="st-key-route-header-shell-"] {
  margin: 0 auto;
  padding: 0;
}

.site-brand-wrap {
  display: flex;
  align-items: center;
  justify-self: start;
  min-width: 0;
}

.site-brand-mark {
  display: none;
}

.site-brand-copy {
  display: flex;
  align-items: center;
}

.site-brand {
  color: var(--text-strong);
  font-family: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", Georgia, serif;
  font-size: 1.68rem;
  font-style: italic;
  font-weight: 700;
  letter-spacing: -0.03em;
}

.site-brand:hover,
.site-brand:visited,
.site-brand:active {
  color: var(--text-strong);
}

.site-brand-subtitle {
  display: none;
}

.site-nav {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: clamp(1.2rem, 2.3vw, 2.25rem);
  padding: 0;
  border: 0;
  background: transparent;
  box-shadow: none;
}

.site-link {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 2.4rem;
  padding: 0;
  border: 0;
  border-radius: 0;
  color: var(--text-secondary);
  font-size: 0.92rem;
  font-weight: 560;
  white-space: nowrap;
  transition: color 0.16s ease, opacity 0.16s ease;
}

.site-link:hover,
.site-link.active {
  color: var(--text-strong);
  background: transparent;
  box-shadow: none;
}

.site-link.active {
  font-weight: 720;
}

.site-utility-nav {
  display: flex;
  align-items: center;
  justify-self: end;
  gap: clamp(0.7rem, 1.3vw, 1.05rem);
  min-width: 0;
}

.site-utility-link {
  color: var(--text-secondary);
  font-size: 0.82rem;
  font-weight: 580;
  white-space: nowrap;
  transition: color 0.16s ease;
}

.site-utility-link:hover,
.site-utility-link.active {
  color: var(--text-strong);
}

.site-utility-link.active {
  font-weight: 720;
}

.site-language-switch {
  display: inline-flex;
  align-items: center;
  gap: 0.56rem;
  margin: 0;
  padding: 0;
  border: 0;
}

.site-language-link {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: auto;
  min-height: 2.4rem;
  padding: 0;
  border: 0;
  border-radius: 0;
  color: var(--text-muted);
  font-size: 0.78rem;
  font-weight: 600;
  letter-spacing: 0.02em;
}

.site-language-link:hover,
.site-language-link.active {
  color: var(--text-strong);
  background: transparent;
}

.site-language-link.active {
  font-weight: 760;
}

div.st-key-home-stage-shell {
  position: relative;
}

.home-market-stage {
  position: relative;
  min-height: clamp(720px, calc(100vh - 5.8rem), 960px);
  margin: -0.55rem calc(-1 * clamp(0rem, 1.4vw, 1.1rem)) 0;
  overflow: hidden;
  isolation: isolate;
}

.home-market-stage::before {
  content: "";
  position: absolute;
  z-index: 0;
  inset: 5% 4% 2%;
  background:
    radial-gradient(ellipse 46% 42% at 52% 66%, color-mix(in srgb, var(--accent-warm) 10%, transparent), transparent 72%),
    radial-gradient(ellipse 34% 30% at 31% 35%, color-mix(in srgb, var(--accent-positive) 7%, transparent), transparent 76%);
  filter: blur(18px);
  pointer-events: none;
}

.home-market-stage::after {
  content: "";
  position: absolute;
  z-index: 0;
  inset: 31% 6% 9%;
  background: radial-gradient(ellipse at center, transparent 38%, color-mix(in srgb, var(--bg-canvas) 82%, transparent) 82%, var(--bg-canvas) 100%);
  pointer-events: none;
}

.market-identity {
  position: absolute;
  z-index: 2;
  top: clamp(4.75rem, 13vh, 8.25rem);
  left: 50%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: min(1120px, 88vw);
  transform: translateX(-50%);
  text-align: center;
}

.market-platform-title {
  margin: 0;
  color: var(--text-strong);
  font-family: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", "Songti SC", "STSong", Georgia, serif;
  font-size: clamp(2.75rem, 4.45vw, 4.65rem);
  font-weight: 760;
  line-height: 1;
  letter-spacing: -0.05em;
  text-wrap: balance;
  text-shadow: 0 12px 42px color-mix(in srgb, var(--bg-canvas) 96%, transparent);
}

.market-news-ticker {
  position: relative;
  width: min(860px, 80vw);
  height: 2rem;
  margin-top: 1.15rem;
  overflow: hidden;
}

.market-news-item.is-static {
  opacity: 1;
  transform: none;
  animation: none;
}

.market-news-loading,
.home-loading-slot {
  opacity: 0.82;
}

.home-loading-slot {
  pointer-events: none;
}

div.st-key-home-stage-shell:has(.home-headlines-fragment) .market-identity.home-loading-slot .market-news-ticker,
div.st-key-home-stage-shell:has(.market-stock-cloud:not(.home-loading-slot)) .market-stock-cloud.home-loading-slot,
div.st-key-home-stage-shell:has(.market-lens:not(.home-loading-slot)) .market-lens.home-loading-slot {
  visibility: hidden;
}

div.st-key-home-stage-shell [data-testid="stElementContainer"]:has(.home-headlines-fragment),
div.st-key-home-stage-shell [data-testid="stElementContainer"]:has(.market-stock-cloud:not(.home-loading-slot)),
div.st-key-home-stage-shell [data-testid="stElementContainer"]:has(.market-lens:not(.home-loading-slot)) {
  position: static;
}

.home-headlines-fragment .market-platform-title {
  visibility: hidden;
}

.market-lens-scene.is-loading {
  opacity: 1;
  transform: none;
  animation: none;
}

.market-news-item {
  position: absolute;
  inset: 0;
  display: block;
  overflow: hidden;
  color: var(--text-secondary);
  font-size: clamp(0.82rem, 1.1vw, 1rem);
  font-weight: 580;
  line-height: 2rem;
  letter-spacing: 0.01em;
  text-align: center;
  text-overflow: ellipsis;
  white-space: nowrap;
  opacity: 0;
  transform: translateY(12px);
  animation: market-news-hop 24s cubic-bezier(0.22, 0.72, 0.22, 1) infinite;
  will-change: transform, opacity, filter;
}

.market-stock-cloud {
  position: absolute;
  z-index: 2;
  top: clamp(18.2rem, 34vh, 21rem);
  left: 50%;
  width: min(920px, 76vw);
  height: 224px;
  transform: translateX(-50%);
  animation: market-stock-enter 720ms cubic-bezier(0.22, 0.72, 0.22, 1) both;
}

.market-stock-cloud::before {
  content: "";
  position: absolute;
  inset: -25% 22%;
  background: radial-gradient(ellipse at center, color-mix(in srgb, var(--accent-warm) 9%, transparent), transparent 73%);
  filter: blur(18px);
  pointer-events: none;
}

.market-stock-focus {
  position: absolute;
  z-index: 2;
  top: 45%;
  left: 50%;
  width: min(460px, 44vw);
  transform: translate(-50%, -50%);
  text-align: center;
}

.market-stock-eyebrow {
  display: block;
  margin-bottom: 0.35rem;
  color: var(--text-muted);
  font-size: 0.64rem;
  font-weight: 740;
  letter-spacing: 0.13em;
  text-transform: uppercase;
}

.market-stock-focus-line {
  display: flex;
  align-items: baseline;
  justify-content: center;
  gap: 0.7rem;
  margin-top: 0.28rem;
}

.market-stock-company {
  display: block;
  color: var(--text-strong);
  font-family: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", "Songti SC", "STSong", Georgia, serif;
  font-size: clamp(1.6rem, 2.35vw, 2.35rem);
  font-weight: 760;
  letter-spacing: -0.035em;
  line-height: 1;
}

.market-stock-focus-line span {
  color: var(--text-secondary);
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-size: 0.68rem;
  font-weight: 700;
  letter-spacing: 0.04em;
}

.market-stock-focus-line b {
  color: var(--text-muted);
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-size: 1rem;
  font-variant-numeric: tabular-nums;
  font-weight: 760;
}

.market-stock-focus.is-positive .market-stock-focus-line b {
  color: var(--accent-positive);
}

.market-stock-focus.is-negative .market-stock-focus-line b {
  color: var(--accent-danger);
}

.market-candles {
  position: relative;
  width: 100%;
  height: 86px;
  margin-top: 0.52rem;
}

.market-candle-grid-line {
  position: absolute;
  right: 0;
  left: 0;
  display: block;
  height: 1px;
  overflow: hidden;
  border-top: 1px dashed color-mix(in srgb, var(--surface-line) 72%, transparent);
}

.market-candle-wick,
.market-candle-body {
  position: absolute;
  display: block;
  overflow: hidden;
  transform: translateX(-50%);
}

.market-candle-wick {
  width: 2px;
}

.market-candle-body {
  min-height: 2px;
}

.market-candle-wick.is-up,
.market-candle-body.is-up { background: var(--accent-positive); }

.market-candle-wick.is-down,
.market-candle-body.is-down { background: var(--accent-danger); }

.market-candles-empty {
  display: grid;
  place-items: center;
  height: 62px;
  margin-top: 0.65rem;
  border-top: 1px dashed var(--surface-line);
  border-bottom: 1px dashed var(--surface-line);
  color: var(--text-muted);
  font-size: 0.66rem;
  letter-spacing: 0.08em;
}

.market-stock-empty,
.market-leaders-empty {
  margin: 0;
  color: var(--text-muted);
  font-size: 0.78rem;
  font-weight: 620;
  letter-spacing: 0.04em;
  text-align: center;
}

.market-stock-empty {
  position: absolute;
  top: 48%;
  left: 50%;
  transform: translate(-50%, -50%);
}

.market-leaders-empty {
  grid-column: 1 / -1;
  padding: 1rem 0;
}

.market-stock-orbit {
  position: absolute;
  z-index: 2;
  display: flex;
  align-items: baseline;
  gap: 0.48rem;
  color: var(--text-secondary);
  text-decoration: none !important;
  transition: color 180ms ease, transform 180ms ease;
}

.market-stock-orbit:hover {
  color: var(--text-strong);
  transform: translateY(-3px);
}

.market-stock-orbit strong {
  color: inherit;
  font-size: clamp(0.86rem, 1.15vw, 1rem);
  font-weight: 760;
  letter-spacing: 0.02em;
}

.market-stock-orbit small {
  color: var(--text-muted);
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-size: 0.58rem;
  font-weight: 700;
  letter-spacing: 0.04em;
}

.market-stock-orbit span {
  color: var(--text-muted);
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-size: 0.67rem;
  font-variant-numeric: tabular-nums;
  font-weight: 700;
}

.market-stock-orbit.is-positive span { color: var(--accent-positive); }
.market-stock-orbit.is-negative span { color: var(--accent-danger); }

.market-stock-orbit.slot-1 { top: 19%; left: 2%; }
.market-stock-orbit.slot-2 { top: 8%; right: 3%; }
.market-stock-orbit.slot-3 { bottom: 24%; left: 13%; }
.market-stock-orbit.slot-4 { right: 11%; bottom: 19%; }

div.st-key-home-stage-shell div.st-key-home-stock-controls {
  position: absolute;
  z-index: 20;
  top: clamp(32rem, 56vh, 35.5rem);
  left: 50%;
  width: 230px;
  margin: 0;
  transform: translateX(-50%);
}

div.st-key-home-stage-shell div.st-key-home-stock-controls [data-testid="stHorizontalBlock"] {
  gap: 0.4rem;
}

div.st-key-home-stage-shell div.st-key-home-stock-controls [data-testid="stColumn"] {
  min-width: 0;
}

div.st-key-home-stage-shell div.st-key-home-stock-controls .stButton button {
  min-height: 2rem;
  height: 2rem;
  padding: 0.28rem 0.48rem;
  border: 1px solid var(--surface-line-strong);
  border-radius: 7px;
  color: var(--text-primary);
  background: color-mix(in srgb, var(--surface-sheet) 62%, transparent);
  box-shadow: none;
  font-size: 0.68rem;
  font-weight: 700;
  line-height: 1;
  white-space: nowrap;
  transition: color 180ms ease, border-color 180ms ease, transform 180ms ease;
}

div.st-key-home-stage-shell div.st-key-home-stock-controls .stButton button[kind="primary"] {
  color: var(--text-strong);
  border-color: var(--surface-line-strong);
  background: var(--surface-sheet);
  box-shadow: 0 5px 14px color-mix(in srgb, var(--text-strong) 7%, transparent);
}

div.st-key-home-stage-shell div.st-key-home-stock-controls .stButton button:hover {
  color: var(--text-strong);
  border-color: var(--text-muted);
  transform: translateY(-2px);
}

.market-lens {
  position: absolute;
  z-index: 2;
  left: 50%;
  bottom: clamp(0.9rem, 2vh, 1.75rem);
  width: min(1160px, 89vw);
  height: clamp(310px, 35vh, 350px);
  transform: translateX(-50%);
}

.market-lens::before {
  content: "";
  position: absolute;
  z-index: -1;
  inset: -18% -8%;
  background: radial-gradient(ellipse at center, color-mix(in srgb, var(--surface-sheet) 58%, transparent), transparent 70%);
  filter: blur(22px);
  pointer-events: none;
}

.market-lens-scene {
  position: absolute;
  inset: 0 0 2.65rem;
  display: flex;
  flex-direction: column;
  justify-content: center;
  opacity: 0;
  transform: translate3d(0, 12px, 0);
  animation: market-lens-cycle 24s cubic-bezier(0.22, 0.72, 0.22, 1) infinite;
  animation-delay: var(--scene-delay);
  will-change: opacity, transform, filter;
}

.market-lens-heading {
  display: flex;
  align-items: end;
  justify-content: space-between;
  gap: 2rem;
  margin-bottom: clamp(1.5rem, 2.8vh, 2.25rem);
  padding: 0 0.25rem;
}

.market-lens-heading > span {
  color: var(--accent-warm);
  font-size: 0.68rem;
  font-weight: 760;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

.market-lens-heading > strong {
  color: var(--text-secondary);
  font-size: clamp(0.9rem, 1.25vw, 1.05rem);
  font-weight: 620;
  letter-spacing: -0.01em;
  text-align: right;
}

.market-index-strip {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  align-items: stretch;
}

.market-index-item {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 0.38rem 0.75rem;
  min-width: 0;
  padding: 0.3rem clamp(1rem, 2.2vw, 1.8rem) 0.7rem;
  transition: transform 180ms ease;
}

.market-index-item + .market-index-item::before {
  content: "";
  position: absolute;
  top: 8%;
  bottom: 7%;
  left: 0;
  width: 1px;
  background: linear-gradient(180deg, transparent, var(--surface-line-strong), transparent);
}

.market-index-item:hover {
  transform: translateY(-3px);
}

.market-item-region {
  grid-column: 1 / -1;
  color: var(--text-muted);
  font-size: 0.66rem;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.market-index-item strong {
  grid-column: 1 / -1;
  overflow: hidden;
  color: var(--text-primary);
  font-size: clamp(0.92rem, 1.2vw, 1.08rem);
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.market-item-quote {
  overflow: hidden;
  color: var(--text-strong);
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-size: clamp(1rem, 1.5vw, 1.32rem);
  font-variant-numeric: tabular-nums;
  font-weight: 720;
  letter-spacing: -0.04em;
  text-overflow: ellipsis;
}

.market-item-change {
  align-self: end;
  color: var(--text-muted);
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-size: 0.75rem;
  font-variant-numeric: tabular-nums;
  font-weight: 700;
  white-space: nowrap;
}

.is-positive .market-item-change {
  color: var(--accent-positive);
}

.is-negative .market-item-change {
  color: var(--accent-danger);
}

.market-leader-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  column-gap: clamp(2rem, 5vw, 5rem);
}

.market-leader-item {
  display: grid;
  grid-template-columns: 2rem minmax(0, 1fr) auto auto auto;
  align-items: center;
  gap: clamp(0.65rem, 1.4vw, 1.15rem);
  min-width: 0;
  padding: 0.9rem 0.25rem;
  border-bottom: 1px solid var(--surface-line);
  transition: padding 180ms ease;
}

.market-leader-item:hover {
  padding-left: 0.6rem;
}

.market-leader-rank,
.market-leader-region {
  color: var(--text-muted);
  font-size: 0.68rem;
  font-weight: 720;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.market-leader-name {
  display: flex;
  align-items: baseline;
  min-width: 0;
  overflow: hidden;
  color: var(--text-secondary);
  font-size: 0.8rem;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.market-leader-name strong {
  margin-right: 0.55rem;
  color: var(--text-strong);
  font-size: 0.95rem;
}

.market-leader-price {
  color: var(--text-primary);
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-size: 0.86rem;
  font-variant-numeric: tabular-nums;
}

.market-temperature-body {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(420px, 0.8fr);
  align-items: end;
  gap: clamp(2rem, 5vw, 5rem);
}

.market-temperature-statement strong {
  display: block;
  margin-bottom: 0.6rem;
  color: var(--text-strong);
  font-family: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", "Songti SC", "STSong", Georgia, serif;
  font-size: clamp(2.5rem, 5vw, 4.7rem);
  font-weight: 760;
  letter-spacing: -0.055em;
  line-height: 0.98;
}

.market-temperature-body.is-positive .market-temperature-statement strong {
  color: var(--accent-positive);
}

.market-temperature-body.is-negative .market-temperature-statement strong {
  color: var(--accent-danger);
}

.market-temperature-statement span {
  color: var(--text-secondary);
  font-size: 0.86rem;
}

.market-temperature-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  margin: 0;
}

.market-temperature-metrics > div {
  position: relative;
  padding-left: clamp(1rem, 2vw, 1.7rem);
}

.market-temperature-metrics > div + div::before {
  content: "";
  position: absolute;
  top: 6%;
  bottom: 7%;
  left: 0;
  width: 1px;
  background: linear-gradient(180deg, transparent, var(--surface-line-strong), transparent);
}

.market-temperature-metrics dt {
  margin-bottom: 0.35rem;
  color: var(--text-muted);
  font-size: 0.68rem;
  font-weight: 680;
}

.market-temperature-metrics dd {
  margin: 0;
  color: var(--text-strong);
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-size: clamp(1.05rem, 1.65vw, 1.42rem);
  font-variant-numeric: tabular-nums;
  font-weight: 720;
}

.market-lens-progress {
  position: absolute;
  right: 0.25rem;
  bottom: 1.85rem;
  display: flex;
  gap: 0.42rem;
}

.market-lens-progress i {
  display: block;
  width: 1.9rem;
  height: 2px;
  overflow: hidden;
  background: var(--surface-line-strong);
}

.market-lens-progress i::after {
  content: "";
  display: block;
  width: 100%;
  height: 100%;
  background: var(--text-strong);
  opacity: 0;
  transform: scaleX(0);
  transform-origin: left;
  animation: market-lens-progress 24s linear infinite;
  animation-delay: var(--step-delay);
}

.market-lens-source {
  position: absolute;
  bottom: 0;
  left: 0.25rem;
  max-width: calc(100% - 8rem);
  margin: 0;
  overflow: hidden;
  color: var(--text-muted);
  font-size: 0.66rem;
  letter-spacing: 0.03em;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@keyframes market-lens-cycle {
  0%, 30% { opacity: 1; filter: blur(0); transform: translate3d(0, 0, 0); }
  34%, 96% { opacity: 0; filter: blur(3px); transform: translate3d(0, -8px, 0); }
  100% { opacity: 1; filter: blur(0); transform: translate3d(0, 0, 0); }
}

@keyframes market-lens-progress {
  0% { opacity: 1; transform: scaleX(0); }
  30% { opacity: 1; transform: scaleX(1); }
  34%, 96% { opacity: 0; transform: scaleX(1); }
  100% { opacity: 1; transform: scaleX(0); }
}

@keyframes market-stock-enter {
  from { opacity: 0; transform: translate3d(-50%, 16px, 0); }
  to { opacity: 1; transform: translate3d(-50%, 0, 0); }
}

@keyframes market-news-hop {
  0% {
    opacity: 0;
    filter: blur(3px);
    transform: translateY(12px);
  }
  2%, 22% {
    opacity: 1;
    filter: blur(0);
    transform: translateY(0);
  }
  27%, 100% {
    opacity: 0;
    filter: blur(2px);
    transform: translateY(-10px);
  }
}

.page-kicker {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  color: var(--accent-warm);
  font-size: 0.8rem;
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.page-kicker::before {
  content: "";
  width: 1.7rem;
  height: 1px;
  background: rgba(186, 115, 73, 0.38);
}

.entry-title {
  margin: 1rem 0 0.85rem;
  color: var(--text-strong);
  font-family: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", Georgia, serif;
  line-height: 0.96;
  letter-spacing: -0.05em;
}

.entry-title {
  font-size: clamp(2.3rem, 4.6vw, 3.4rem);
}

.entry-intro {
  max-width: 780px;
  margin: 0 0 1.6rem;
}

.action-card {
  max-width: 470px;
  margin-top: 1.55rem;
  padding: 1.45rem 1.5rem;
  border: 1px solid var(--surface-line);
  border-radius: 28px;
  background: var(--surface-sheet);
  box-shadow: var(--shadow-soft);
}

.action-card-kicker,
.surface-kicker {
  color: var(--text-muted);
  font-size: 0.79rem;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.action-card-title {
  margin: 0.45rem 0 0.35rem;
  color: var(--text-strong);
  font-size: 1.12rem;
  font-weight: 700;
}

.action-card-copy,
.surface-copy,
.section-copy {
  margin: 0;
  color: var(--text-secondary);
  font-size: 0.95rem;
  line-height: 1.68;
}

.cta-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  margin-top: 1rem;
}

.cta-link {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 44px;
  padding: 0.72rem 1.16rem;
  border: 1px solid transparent;
  border-radius: 999px;
  background: var(--accent-primary);
  color: var(--text-inverse);
  font-weight: 700;
  transition: transform 0.15s ease, opacity 0.15s ease, background 0.15s ease;
}

.cta-link:hover {
  transform: translateY(-1px);
  opacity: 0.97;
}

.cta-link:hover,
.cta-link:visited,
.cta-link:active {
  color: var(--text-inverse);
}

.cta-link.secondary {
  border-color: var(--surface-line-strong);
  background: rgba(255, 252, 247, 0.78);
  color: var(--text-strong);
}

.cta-link.secondary:hover,
.cta-link.secondary:visited,
.cta-link.secondary:active {
  color: var(--text-strong);
}

.cta-link.pill-secondary {
  min-height: 36px;
  padding: 0.42rem 0.9rem;
  border-color: rgba(123, 95, 64, 0.16);
  background: rgba(255, 252, 247, 0.9);
  color: var(--text-strong);
  font-size: 0.84rem;
  font-weight: 700;
  box-shadow: none;
}

.cta-link.pill-secondary:hover,
.cta-link.pill-secondary:visited,
.cta-link.pill-secondary:active {
  color: var(--text-strong);
}

.hero-note-list {
  display: grid;
  gap: 0.75rem;
  margin-top: 1.2rem;
}

.hero-note-item {
  display: flex;
  gap: 0.75rem;
  align-items: flex-start;
  color: var(--text-secondary);
  font-size: 0.95rem;
  line-height: 1.65;
}

.hero-note-item strong {
  min-width: 2rem;
  color: var(--text-strong);
  font-size: 0.84rem;
}

.entry-path {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin: 1.1rem 0 0.15rem;
}

.entry-path-step {
  display: inline-flex;
  align-items: center;
  gap: 0.38rem;
  min-height: 30px;
  padding: 0.3rem 0.62rem;
  border-radius: 999px;
  background: var(--accent-primary-soft);
  color: var(--text-secondary);
  font-size: 0.78rem;
  font-weight: 650;
}

.entry-path-step strong {
  color: var(--accent-warm);
  font-size: 0.7rem;
  letter-spacing: 0.06em;
}

.showcase-board {
  position: relative;
  min-height: 650px;
  padding: 1.5rem;
  border: 1px solid var(--surface-line);
  border-radius: 34px;
  background: linear-gradient(180deg, rgba(255, 251, 245, 0.96), rgba(244, 231, 211, 0.94));
  box-shadow: var(--shadow-board);
  overflow: hidden;
}

.showcase-board::before {
  content: "";
  position: absolute;
  inset: 0;
  background:
    radial-gradient(circle at 12% 12%, rgba(255, 255, 255, 0.78), transparent 22%),
    radial-gradient(circle at 86% 16%, rgba(251, 239, 222, 0.6), transparent 20%),
    radial-gradient(circle at 58% 72%, rgba(232, 204, 170, 0.24), transparent 24%);
  pointer-events: none;
}

.home-showcase {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  min-height: auto;
  margin-top: clamp(1.1rem, 2vw, 1.55rem);
}

.home-showcase-grid {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: minmax(0, 1.12fr) minmax(220px, 0.88fr);
  gap: 1rem;
}

.home-showcase-stack {
  display: grid;
  gap: 1rem;
}

.board-chip {
  position: relative;
  z-index: 1;
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  padding: 0.38rem 0.76rem;
  border-radius: 999px;
  background: rgba(255, 251, 245, 0.84);
  color: var(--text-secondary);
  font-size: 0.81rem;
  font-weight: 700;
}

.board-chip::before {
  content: "";
  width: 0.38rem;
  height: 0.38rem;
  border-radius: 999px;
  background: var(--accent-warm);
}

.board-main-sheet,
.floating-sheet {
  position: absolute;
  border: 1px solid var(--surface-line);
  border-radius: 24px;
  background: rgba(255, 249, 241, 0.92);
  box-shadow: var(--shadow-soft);
}

.board-main-sheet {
  left: 2rem;
  right: 2rem;
  bottom: 1.9rem;
  padding: 1.28rem 1.34rem;
}

.floating-sheet {
  padding: 1rem 1.05rem;
}

.home-showcase .floating-sheet,
.home-showcase .board-main-sheet {
  position: relative;
  left: auto;
  right: auto;
  top: auto;
  bottom: auto;
  width: auto !important;
}

.home-showcase .sheet-market {
  min-height: 216px;
  padding: 1.1rem 1.15rem;
}

.home-showcase .sheet-workflow,
.home-showcase .sheet-progress {
  min-height: 132px;
}

.floating-sheet-title {
  color: var(--text-strong);
  font-size: 1rem;
  font-weight: 700;
}

.floating-sheet-copy {
  margin-top: 0.35rem;
  color: var(--text-secondary);
  font-size: 0.91rem;
  line-height: 1.6;
}

.board-main-sheet h3 {
  margin: 0.45rem 0 0.35rem;
  color: var(--text-strong);
  font-size: 1.3rem;
  font-weight: 700;
}

.board-main-sheet p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 0.94rem;
  line-height: 1.7;
}

.board-flow-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.9rem;
}

.board-flow-row span {
  display: inline-flex;
  align-items: center;
  gap: 0.38rem;
  min-height: 34px;
  padding: 0.38rem 0.8rem;
  border-radius: 999px;
  background: var(--accent-primary-soft);
  color: var(--text-primary);
  font-size: 0.84rem;
  font-weight: 600;
}

.board-flow-row span strong {
  color: var(--accent-warm);
  font-size: 0.72rem;
  letter-spacing: 0.06em;
}

.board-flow-row.compact {
  margin-top: 0.75rem;
}

.board-flow-row.compact span {
  min-height: 30px;
  padding: 0.32rem 0.72rem;
  font-size: 0.8rem;
}

.board-micro-list {
  display: grid;
  gap: 0.45rem;
  margin-top: 0.7rem;
}

.board-micro-item {
  display: flex;
  justify-content: space-between;
  gap: 0.8rem;
  color: var(--text-secondary);
  font-size: 0.85rem;
}

.board-micro-item strong {
  color: var(--text-strong);
  font-weight: 700;
}

.home-showcase .board-main-sheet {
  z-index: 1;
  margin-top: 0.2rem;
}

.board-footnote {
  margin-top: 0.75rem !important;
  color: var(--text-muted) !important;
  font-size: 0.88rem !important;
  line-height: 1.55 !important;
}

div[class*="st-key-single-action-card"],
div[class*="st-key-multi-action-card"] {
  padding: 1.4rem 1.45rem 1.3rem;
  border: 1px solid var(--surface-line);
  border-radius: 28px;
  background: var(--surface-sheet);
  box-shadow: var(--shadow-soft);
}

div[class*="st-key-single-action-card"] [data-testid="stFileUploaderDropzone"],
div[class*="st-key-multi-action-card"] [data-testid="stFileUploaderDropzone"] {
  min-height: 8.5rem;
}

div[class*="st-key-single-action-card"] [data-testid="stFileUploaderDropzone"],
div[class*="st-key-multi-action-card"] [data-testid="stFileUploaderDropzone"] {
  position: relative;
  display: block;
  min-height: 7.25rem;
}

div[class*="st-key-single-action-card"] [data-testid="stFileUploaderDropzone"]::before,
div[class*="st-key-multi-action-card"] [data-testid="stFileUploaderDropzone"]::before {
  content: "Drop a CSV file here, or click to select one";
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  padding: 1rem;
  color: var(--text-secondary);
  font-size: 0.9rem;
  font-weight: 620;
  line-height: 1.55;
  text-align: center;
  pointer-events: none;
}

body:has(.site-language-link[lang="zh-CN"].active) div[class*="st-key-single-action-card"] [data-testid="stFileUploaderDropzone"]::before,
body:has(.site-language-link[lang="zh-CN"].active) div[class*="st-key-multi-action-card"] [data-testid="stFileUploaderDropzone"]::before {
  content: "将 CSV 文件拖放到此处，或点击选择文件";
}

div[class*="st-key-multi-action-card"] [data-testid="stFileUploaderDropzone"]::before {
  content: "Drop CSV files here, or click to select files";
}

body:has(.site-language-link[lang="zh-CN"].active) div[class*="st-key-multi-action-card"] [data-testid="stFileUploaderDropzone"]::before {
  content: "将 CSV 文件拖放到此处，或点击选择文件";
}

div[class*="st-key-single-action-card"] [data-testid="stFileUploaderDropzone"] > span,
div[class*="st-key-multi-action-card"] [data-testid="stFileUploaderDropzone"] > span {
  position: absolute;
  inset: 0;
  z-index: 1;
  display: block;
}

div[class*="st-key-single-action-card"] [data-testid="stFileUploaderDropzone"] > span > button,
div[class*="st-key-multi-action-card"] [data-testid="stFileUploaderDropzone"] > span > button {
  position: absolute;
  inset: 0;
  width: 100%;
  min-width: 0;
  height: 100%;
  min-height: 0;
  padding: 0;
  border: 0 !important;
  background: transparent !important;
  opacity: 0;
  cursor: pointer;
}

div[class*="st-key-single-action-card"] [data-testid="stFileUploaderDropzone"] > div,
div[class*="st-key-multi-action-card"] [data-testid="stFileUploaderDropzone"] > div {
  display: none;
}

div[class*="st-key-single-showcase-board"],
div[class*="st-key-multi-showcase-board"] {
  padding: 1.35rem 1.4rem 1.25rem;
  border: 1px solid var(--surface-line);
  border-radius: 32px;
  background: linear-gradient(180deg, rgba(255, 251, 245, 0.96), rgba(244, 231, 211, 0.94));
  box-shadow: var(--shadow-board);
}

div[class*="st-key-single-showcase-board"],
div[class*="st-key-multi-showcase-board"] {
  padding-bottom: 0.45rem;
  background: var(--surface-sheet);
}

div[class*="st-key-single-recommend-sheet"],
div[class*="st-key-multi-recommend-sheet"] {
  margin-top: 1rem;
  padding: 1.12rem 1.15rem 0.8rem;
  border: 1px solid var(--surface-line);
  border-radius: 24px;
  background: var(--surface-sheet);
  box-shadow: var(--shadow-soft);
}

div[class*="st-key-single-stock-basic-section"],
div[class*="st-key-single-stock-strategy-section"],
div[class*="st-key-multi-stock-basic-section"],
div[class*="st-key-multi-stock-strategy-section"] {
  padding: 1.45rem 1.5rem 1.35rem;
  border: 1px solid var(--surface-line);
  border-radius: 30px;
  background: rgba(255, 251, 245, 0.92);
  box-shadow: var(--shadow-soft);
}

div[class*="st-key-single-stock-analysis-hero"],
div[class*="st-key-multi-stock-analysis-hero"] {
  padding: 1.55rem 1.6rem 1.35rem;
  border: 1px solid var(--surface-line);
  border-radius: 30px;
  background: linear-gradient(180deg, rgba(255, 251, 245, 0.98), rgba(248, 237, 220, 0.92));
  box-shadow: var(--shadow-soft);
}

div[class*="st-key-single-stock-analysis-hero"] [data-testid="stHorizontalBlock"],
div[class*="st-key-multi-stock-analysis-hero"] [data-testid="stHorizontalBlock"] {
  align-items: stretch;
}

div[class*="st-key-single-stock-header-range"],
div[class*="st-key-multi-stock-header-range"] {
  margin-top: 1rem;
  padding: 0.95rem 1rem 0.22rem;
  border: 1px solid rgba(123, 95, 64, 0.1);
  border-radius: 24px;
  background: rgba(255, 249, 241, 0.74);
}

div[class*="st-key-single-stock-header-range"] [data-testid="stDateInputField"],
div[class*="st-key-multi-stock-header-range"] [data-testid="stDateInputField"] {
  min-height: 54px;
  border-radius: 22px !important;
  background: rgba(255, 251, 245, 0.94) !important;
  box-shadow: none;
}

div[class*="st-key-single-stock-chart-frame"],
div[class*="st-key-multi-stock-chart-frame"] {
  padding: 1.05rem 1.1rem 0.82rem;
  border-radius: 26px;
  border: 1px solid rgba(123, 95, 64, 0.1);
  background: rgba(255, 252, 247, 0.94);
}

div[class*="st-key-multi-stock-basic-panel"],
div[class*="st-key-multi-stock-strategy-panel"] {
  padding: 1.12rem 1.15rem 1rem;
  border-radius: 26px;
  border: 1px solid rgba(123, 95, 64, 0.1);
  background: rgba(255, 252, 247, 0.94);
}

.surface-title {
  margin: 0.35rem 0 0.25rem;
  color: var(--text-strong);
  font-size: 1.24rem;
  font-weight: 700;
}

/* Full course report rendered directly inside the Strategy Lab page DOM. */
.native-report-shell {
  width: 100%;
  margin: 0.35rem auto 4rem;
  color: var(--text-primary);
  font-size: 0.98rem;
  line-height: 1.78;
}

.native-report-shell.native-report-intro {
  margin-bottom: 0;
}

.native-report-shell.native-report-reading {
  margin-top: 0.65rem;
}

.block-container:has(.native-report-intro) {
  max-width: 1220px;
}

.native-report-intro#report-top,
.native-report-reading section {
  scroll-margin-top: 1.25rem;
}

.report-scroll-rail {
  display: none;
}

.report-back-top {
  position: fixed;
  right: clamp(1rem, 2.4vw, 2rem);
  bottom: clamp(1rem, 2.4vw, 2rem);
  z-index: 30;
  display: grid;
  width: 2.65rem;
  height: 2.65rem;
  place-items: center;
  color: var(--text-strong);
  border: 1px solid var(--surface-line-strong);
  border-radius: 50%;
  background: var(--surface-frost);
  box-shadow: var(--shadow-soft);
  font-size: 1.15rem;
  line-height: 1;
  text-decoration: none;
  backdrop-filter: blur(12px);
  transition: transform 160ms ease, border-color 160ms ease;
}

.report-back-top:hover {
  border-color: var(--accent-warm);
  transform: translateY(-2px);
}

.report-search-results {
  display: grid;
  gap: 0.65rem;
  margin: 0.85rem 0 1.25rem;
}

.report-search-result {
  display: grid;
  gap: 0.25rem;
  padding: 0.8rem 0.95rem;
  color: var(--text-strong);
  border: 1px solid var(--surface-line);
  border-left: 3px solid var(--accent-warm);
  background: var(--surface-sheet);
  text-decoration: none;
}

.report-search-result:hover,
.report-search-result:focus-visible {
  border-color: var(--accent-warm);
  background: var(--surface-frost);
}

.report-search-result strong {
  font-size: 0.9rem;
}

.report-search-result span {
  color: var(--text-muted);
  font-size: 0.78rem;
  line-height: 1.55;
}

.report-scroll-rail a.is-active {
  color: var(--text-strong);
  border-color: var(--accent-warm);
  background: var(--surface-sheet);
  opacity: 1;
}

@keyframes report-rail-current {
  0%, 100% {
    color: var(--text-muted);
    border-color: transparent;
    background: transparent;
    opacity: 0.62;
  }
  3%, 97% {
    color: var(--text-strong);
    border-color: var(--accent-warm);
    background: var(--surface-sheet);
    opacity: 1;
  }
}

@keyframes report-rail-sub-current {
  0%, 100% {
    max-height: 0;
    margin-top: 0;
    opacity: 0;
  }
  1%, 99% {
    max-height: 64rem;
    margin-top: 0.12rem;
    opacity: 1;
  }
}

@media (min-width: 1600px) {
  .report-scroll-rail {
    position: fixed;
    top: 6.25rem;
    left: max(0.75rem, calc(50vw - 786px));
    z-index: 20;
    display: block;
    width: 9.75rem;
    max-height: calc(100vh - 8rem);
    padding: 0.75rem 0.65rem;
    overflow-y: auto;
    border: 1px solid var(--surface-line);
    border-radius: 18px;
    background: var(--surface-frost);
    box-shadow: var(--shadow-soft);
    scrollbar-width: thin;
    backdrop-filter: blur(12px);
  }

  .report-reading-document {
    min-width: 0;
  }

  .report-scroll-rail-label {
    position: sticky;
    top: -0.75rem;
    z-index: 2;
    display: block;
    margin: 0;
    padding: 0.35rem 0.4rem 0.55rem;
    color: var(--text-muted);
    background: var(--surface-frost);
    font-size: 0.7rem;
    font-weight: 750;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  .report-scroll-rail nav {
    display: grid;
    gap: 0.45rem;
  }

  .report-scroll-rail-group {
    padding-bottom: 0.38rem;
    border-bottom: 1px solid var(--surface-line);
  }

  .report-scroll-rail-group:last-child {
    padding-bottom: 0;
    border-bottom: 0;
  }

  .report-scroll-rail-sub {
    display: grid;
    gap: 0.08rem;
    margin-top: 0.12rem;
  }

  .report-scroll-rail a {
    display: block;
    padding: 0.32rem 0.42rem;
    color: var(--text-muted);
    border-left: 2px solid transparent;
    border-radius: 0 8px 8px 0;
    line-height: 1.35;
    text-decoration: none;
    opacity: 0.72;
  }

  .report-scroll-rail-chapter {
    font-size: 0.72rem;
    font-weight: 750;
  }

  .report-scroll-rail-sub-link {
    padding-left: 0.78rem !important;
    font-size: 0.64rem;
    font-weight: 520;
  }

  .report-scroll-rail a:hover {
    color: var(--text-strong);
    background: var(--surface-sheet);
    opacity: 1;
  }

  @supports (animation-timeline: view()) {
    .report-scroll-rail a {
      animation: report-rail-current 1ms linear both;
      animation-range: entry 0% exit 100%;
    }

    .report-scroll-rail-sub {
      overflow: hidden;
      animation: report-rail-sub-current 1ms linear both;
      animation-range: entry 0% exit 100%;
    }
  }
}

.native-report-shell .hero {
  padding: clamp(1.25rem, 2.5vw, 2.35rem) 0 clamp(1.1rem, 2vw, 1.65rem);
  text-align: left;
  border-bottom: 1px solid var(--surface-line);
  background: transparent;
}

.native-report-shell .eyebrow {
  color: var(--accent-warm);
  font-size: 0.78rem;
  font-weight: 750;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.native-report-shell .hero h1 {
  max-width: 900px;
  margin: 0.8rem 0 1rem;
  color: var(--text-strong);
  font-family: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", Georgia, serif;
  font-size: clamp(2.5rem, 5.6vw, 4.8rem);
  line-height: 0.98;
  letter-spacing: -0.055em;
}

.native-report-shell .hero > p {
  max-width: 820px;
  margin: 0;
  color: var(--text-secondary);
  font-size: 1.03rem;
}

.native-report-shell .grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0;
  margin-top: 2rem;
  border-top: 1px solid var(--surface-line);
  border-bottom: 1px solid var(--surface-line);
}

.native-report-shell .card {
  min-width: 0;
  padding: 1.1rem 1.25rem;
  color: var(--text-muted);
  border-right: 1px solid var(--surface-line);
}

.native-report-shell .card:last-child {
  border-right: 0;
}

.native-report-shell .card strong {
  display: block;
  margin-top: 0.35rem;
  color: var(--text-strong);
  font-size: 0.95rem;
}

.native-report-shell .toc {
  margin: 2.5rem 0 3.5rem;
  padding: clamp(1.4rem, 3vw, 2.2rem);
  border: 1px solid var(--surface-line);
  border-radius: 26px;
  background: var(--surface-sheet);
  box-shadow: var(--shadow-soft);
}

.native-report-shell .toc h2 {
  margin: 0 0 1.25rem;
  color: var(--text-strong);
  font-family: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", Georgia, serif;
  font-size: clamp(1.7rem, 3vw, 2.25rem);
}

.native-report-shell .toc > ol {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.7rem 1.25rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.native-report-shell .toc li {
  margin: 0;
}

.native-report-shell .toc details {
  padding: 0.75rem 0;
  border-bottom: 1px solid var(--surface-line);
}

.native-report-shell .toc summary {
  display: flex;
  gap: 0.55rem;
  align-items: flex-start;
  color: var(--text-strong);
  font-weight: 700;
  cursor: pointer;
  list-style: none;
}

.native-report-shell .toc summary::-webkit-details-marker {
  display: none;
}

.native-report-shell .toc summary::before {
  content: "+";
  flex: 0 0 auto;
  color: var(--accent-warm);
  font-size: 1rem;
  line-height: 1.55;
}

.native-report-shell .toc details[open] summary::before {
  content: "−";
}

.native-report-shell .toc a {
  color: inherit;
  text-decoration: none;
}

.native-report-shell .toc .sub-toc {
  margin: 0.7rem 0 0 1.45rem;
  padding-left: 1rem;
  color: var(--text-secondary);
  border-left: 1px solid var(--surface-line-strong);
}

.native-report-shell .toc .sub-toc li {
  margin: 0.28rem 0;
  font-size: 0.86rem;
}

.native-report-shell section {
  padding: clamp(2rem, 4vw, 3.4rem) 0;
  border-top: 1px solid var(--surface-line);
  background: transparent;
  overflow: hidden;
}

.native-report-shell section h2 {
  margin: 0 0 1.25rem;
  color: var(--text-strong);
  font-family: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", Georgia, serif;
  font-size: clamp(1.8rem, 3.4vw, 2.65rem);
  line-height: 1.12;
  letter-spacing: -0.03em;
}

.native-report-shell section h3 {
  margin: 2rem 0 0.75rem;
  color: var(--text-strong);
  font-size: 1.22rem;
}

.native-report-shell section h4 {
  margin: 1.55rem 0 0.6rem;
  color: var(--text-primary);
  font-size: 1rem;
}

.native-report-shell section p,
.native-report-shell section li {
  color: var(--text-secondary);
}

.native-report-shell section a {
  color: var(--accent-warm);
  text-decoration: none;
}

.native-report-shell ul,
.native-report-shell ol {
  padding-left: 1.35rem;
}

.native-report-shell li {
  margin: 0.42rem 0;
}

.native-report-shell .table-wrap {
  max-width: 100%;
  margin: 1.2rem 0;
  overflow-x: auto;
  border: 1px solid var(--surface-line);
  border-radius: 18px;
  background: var(--surface-sheet);
}

.native-report-shell table {
  width: 100%;
  min-width: 680px;
  border-collapse: collapse;
  font-size: 0.86rem;
}

.native-report-shell th,
.native-report-shell td {
  padding: 0.72rem 0.85rem;
  text-align: left;
  vertical-align: top;
  border-bottom: 1px solid var(--surface-line);
  border-right: 1px solid var(--surface-line);
}

.native-report-shell th:last-child,
.native-report-shell td:last-child {
  border-right: 0;
}

.native-report-shell th {
  color: var(--text-strong);
  background: var(--accent-primary-soft);
  font-weight: 750;
}

.native-report-shell td {
  color: var(--text-secondary);
}

.native-report-shell code {
  padding: 0.14rem 0.4rem;
  border-radius: 7px;
  background: var(--accent-primary-soft);
  color: var(--text-strong);
  font-family: "Cascadia Code", Consolas, monospace;
  font-size: 0.86em;
  overflow-wrap: anywhere;
}

.native-report-shell pre {
  max-width: 100%;
  padding: 1rem 1.1rem;
  overflow-x: auto;
  border: 1px solid var(--surface-line);
  border-radius: 16px;
  background: var(--surface-sheet);
}

.native-report-shell pre code {
  padding: 0;
  background: transparent;
}

.native-report-shell blockquote,
.native-report-shell blockquote[style] {
  margin: 1.25rem 0;
  padding: 1rem 1.2rem !important;
  border: 0 !important;
  border-left: 3px solid var(--accent-warm) !important;
  border-radius: 0 14px 14px 0;
  background: var(--accent-primary-soft) !important;
  color: var(--text-primary);
}

.native-report-shell .note,
.native-report-shell .callout,
.native-report-shell .insight {
  margin: 1.2rem 0;
  padding: 1rem 1.15rem;
  border: 1px solid var(--surface-line);
  border-radius: 16px;
  background: var(--surface-sheet);
  color: var(--text-secondary);
}

.native-report-shell .footer {
  margin-top: 2.5rem;
  padding-top: 1.5rem;
  color: var(--text-muted);
  text-align: center;
  border-top: 1px solid var(--surface-line);
}

div[class*="st-key-final-report-search-shell"] {
  margin: 0.15rem 0 0;
}

div[class*="st-key-final-report-search-shell"] [data-testid="stTextInput"] {
  max-width: 760px;
}

div[class*="st-key-final-report-search-shell"] [data-testid="stHorizontalBlock"] {
  flex-wrap: nowrap;
  align-items: center;
  gap: 0.5rem;
}

div[class*="st-key-final-report-search-shell"] [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
  min-width: 0 !important;
}

@media (max-width: 760px) {
  .report-back-top {
    width: 2.35rem;
    height: 2.35rem;
  }

  .native-report-shell .grid,
  .native-report-shell .toc > ol {
    grid-template-columns: 1fr;
  }

  .native-report-shell .card {
    border-right: 0;
    border-bottom: 1px solid var(--surface-line);
  }

  .native-report-shell .card:last-child {
    border-bottom: 0;
  }

  .native-report-shell .toc {
    padding: 1.15rem;
    border-radius: 20px;
  }
}

.entry-section-title {
  margin: 0;
  color: var(--text-strong);
  font-size: 1rem;
  font-weight: 700;
}

.entry-section-copy {
  margin: 0.22rem 0 0;
  color: var(--text-secondary);
  font-size: 0.92rem;
  line-height: 1.62;
}

.section-divider {
  height: 1px;
  margin: 1.15rem 0;
  background: var(--surface-line);
}

.plain-helper {
  margin: 0.55rem 0 0;
  color: var(--text-muted);
  font-size: 0.89rem;
  line-height: 1.6;
}

.selection-note,
.source-note {
  margin: 0.65rem 0 0;
  color: var(--text-secondary);
  font-size: 0.9rem;
  line-height: 1.55;
}

.selection-note strong,
.source-note strong {
  color: var(--text-strong);
}

div[class*="st-key-single-csv-requirements"],
div[class*="st-key-multi-csv-requirements"],
div[class*="st-key-multi-selected-stock-popover"] {
  margin-top: 0.32rem;
}

div[class*="st-key-single-csv-requirements"] button,
div[class*="st-key-multi-csv-requirements"] button,
div[class*="st-key-multi-selected-stock-popover"] [data-testid="stPopoverButton"] {
  width: auto !important;
  min-height: auto !important;
  padding: 0.12rem 0 !important;
  border: 0 !important;
  border-radius: 0 !important;
  background: transparent !important;
  box-shadow: none !important;
  color: var(--accent-warm) !important;
  font-size: 0.9rem !important;
  font-weight: 720 !important;
  line-height: 1.45 !important;
  text-align: left !important;
  transform: none !important;
}

div[class*="st-key-single-csv-requirements"] button:hover,
div[class*="st-key-multi-csv-requirements"] button:hover,
div[class*="st-key-multi-selected-stock-popover"] [data-testid="stPopoverButton"]:hover {
  color: var(--text-strong) !important;
}

div[class*="st-key-single-csv-requirements"] button:focus-visible,
div[class*="st-key-multi-csv-requirements"] button:focus-visible,
div[class*="st-key-multi-selected-stock-popover"] [data-testid="stPopoverButton"]:focus-visible {
  outline: 2px solid var(--accent-warm) !important;
  outline-offset: 3px;
}

div[class*="st-key-single-market-heading-row"] [data-testid="stHorizontalBlock"],
div[class*="st-key-multi-market-heading-row"] [data-testid="stHorizontalBlock"] {
  align-items: center;
}

div[class*="st-key-single-refresh-market-context"] .stButton > button,
div[class*="st-key-multi-refresh-market-context"] .stButton > button {
  min-width: 0;
  width: 100%;
  white-space: nowrap;
}

@media (min-width: 881px) {
  div[class*="st-key-single-entry-split"] > [data-testid="stLayoutWrapper"] > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"],
  div[class*="st-key-multi-entry-split"] > [data-testid="stLayoutWrapper"] > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
    display: flex;
    flex-direction: column;
  }

  div[class*="st-key-single-entry-split"] > [data-testid="stLayoutWrapper"] > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] > [data-testid="stVerticalBlock"],
  div[class*="st-key-single-entry-split"] > [data-testid="stLayoutWrapper"] > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] > [data-testid="stVerticalBlock"] > [data-testid="stLayoutWrapper"],
  div[class*="st-key-multi-entry-split"] > [data-testid="stLayoutWrapper"] > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] > [data-testid="stVerticalBlock"],
  div[class*="st-key-multi-entry-split"] > [data-testid="stLayoutWrapper"] > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] > [data-testid="stVerticalBlock"] > [data-testid="stLayoutWrapper"] {
    display: flex;
    flex: 1 1 auto;
    min-height: 0;
  }

  div[class*="st-key-single-action-card"],
  div[class*="st-key-single-showcase-board"],
  div[class*="st-key-multi-action-card"],
  div[class*="st-key-multi-showcase-board"] {
    flex: 1 1 auto;
  }

  div[class*="st-key-single-showcase-board"] > [data-testid="stLayoutWrapper"]:last-child,
  div[class*="st-key-single-recommend-sheet"],
  div[class*="st-key-single-recommend-sheet"] > [data-testid="stLayoutWrapper"]:last-child,
  div[class*="st-key-single-recommend-scroll"],
  div[class*="st-key-multi-showcase-board"] > [data-testid="stLayoutWrapper"]:last-child,
  div[class*="st-key-multi-recommend-sheet"],
  div[class*="st-key-multi-recommend-sheet"] > [data-testid="stLayoutWrapper"]:last-child,
  div[class*="st-key-multi-recommend-scroll"] {
    flex: 1 1 0;
    min-height: 0;
  }

  div[class*="st-key-single-recommend-scroll"],
  div[class*="st-key-multi-recommend-scroll"] {
    max-height: none;
  }
}

.snapshot-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.8rem;
  margin-top: 1rem;
}

.snapshot-item {
  padding: 0.95rem 1rem;
  border-radius: 20px;
  background: rgba(255, 248, 239, 0.58);
  border: 1px solid rgba(123, 95, 64, 0.08);
  backdrop-filter: blur(8px);
}

.snapshot-label {
  display: block;
  color: var(--text-secondary);
  font-size: 0.82rem;
  font-weight: 700;
}

.snapshot-value {
  display: block;
  margin-top: 0.38rem;
  color: var(--text-strong);
  font-size: 1.16rem;
  font-weight: 700;
}

.snapshot-delta {
  display: block;
  margin-top: 0.22rem;
  color: var(--text-muted);
  font-size: 0.88rem;
  font-weight: 600;
}

.snapshot-delta.up {
  color: var(--accent-danger);
}

.snapshot-delta.down {
  color: var(--accent-positive);
}

div[class*="st-key-single-recommend-scroll"],
div[class*="st-key-multi-recommend-scroll"] {
  max-height: 390px;
  overflow-y: auto;
  padding-right: 0.1rem;
}

div[class*="st-key-single-recommend-scroll"] [data-testid="stHorizontalBlock"],
div[class*="st-key-multi-recommend-scroll"] [data-testid="stHorizontalBlock"],
div[class*="st-key-multi-selected-symbols"] [data-testid="stHorizontalBlock"],
div[class*="st-key-multi-stock-remove-list"] [data-testid="stHorizontalBlock"],
div[class*="st-key-multi-stock-add-list"] [data-testid="stHorizontalBlock"] {
  align-items: center;
}

div[class*="st-key-single-recommend-scroll"] [data-testid="column"],
div[class*="st-key-multi-recommend-scroll"] [data-testid="column"],
div[class*="st-key-multi-selected-symbols"] [data-testid="column"],
div[class*="st-key-multi-stock-remove-list"] [data-testid="column"],
div[class*="st-key-multi-stock-add-list"] [data-testid="column"] {
  display: flex;
  flex-direction: column;
  justify-content: center;
}

div[class*="st-key-single-recommend-scroll"]::-webkit-scrollbar,
div[class*="st-key-multi-recommend-scroll"]::-webkit-scrollbar {
  width: 7px;
}

div[class*="st-key-single-recommend-scroll"]::-webkit-scrollbar-thumb,
div[class*="st-key-multi-recommend-scroll"]::-webkit-scrollbar-thumb {
  background: rgba(149, 122, 91, 0.42);
  border-radius: 999px;
}

.recommend-row,
.selection-row,
.upload-row {
  padding: 0.82rem 0;
  border-bottom: 1px solid rgba(123, 95, 64, 0.1);
}

.recommend-row-title,
.selection-row-title,
.upload-row-title {
  color: var(--text-strong);
  font-size: 0.98rem;
  font-weight: 700;
  line-height: 1.35;
}

.recommend-row-meta,
.selection-row-meta,
.upload-row-meta {
  margin-top: 0.18rem;
  color: var(--text-secondary);
  font-size: 0.9rem;
  line-height: 1.55;
}

div[class*="st-key-single-recommend-scroll"] .stButton,
div[class*="st-key-multi-recommend-scroll"] .stButton,
div[class*="st-key-multi-selected-symbols"] .stButton,
div[class*="st-key-multi-stock-remove-list"] .stButton,
div[class*="st-key-multi-stock-add-list"] .stButton {
  display: flex;
  justify-content: flex-end;
}

div[class*="st-key-single-recommend-scroll"] .stButton > button,
div[class*="st-key-multi-recommend-scroll"] .stButton > button,
div[class*="st-key-multi-selected-symbols"] .stButton > button {
  min-width: 84px;
  min-height: 34px;
  padding: 0.32rem 0.8rem;
  font-size: 0.82rem;
  font-weight: 700;
}

div[class*="st-key-multi-stock-remove-list"] .stButton > button,
div[class*="st-key-multi-stock-add-list"] .stButton > button {
  min-width: 72px;
  min-height: 38px;
  padding: 0.3rem 0.72rem;
  border-radius: 16px !important;
  font-size: 0.82rem;
  box-shadow: none;
}

div[class*="st-key-multi-stock-remove-list"] .stButton > button {
  border-color: rgba(179, 74, 69, 0.22) !important;
  background: rgba(255, 245, 243, 0.92) !important;
  color: var(--accent-danger) !important;
}

div[class*="st-key-multi-stock-remove-list"] .stButton > button:hover {
  border-color: rgba(179, 74, 69, 0.34) !important;
  background: rgba(255, 250, 247, 0.98) !important;
}

div[class*="st-key-multi-stock-add-list"] .stButton > button {
  border-color: rgba(78, 124, 89, 0.18) !important;
  background: rgba(244, 250, 245, 0.92) !important;
  color: var(--accent-positive) !important;
}

div[class*="st-key-multi-stock-add-list"] .stButton > button:hover {
  border-color: rgba(78, 124, 89, 0.3) !important;
  background: rgba(250, 253, 250, 0.98) !important;
}

.analysis-page-shell {
  display: grid;
  gap: 1.6rem;
  margin: 1.1rem 0 0.35rem;
}

.analysis-hero {
  padding: 1.55rem 1.6rem;
  border: 1px solid var(--surface-line);
  border-radius: 30px;
  background: linear-gradient(180deg, rgba(255, 251, 245, 0.98), rgba(248, 237, 220, 0.92));
  box-shadow: var(--shadow-soft);
}

.analysis-hero-topline {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.7rem;
  margin-bottom: 0.9rem;
}

.analysis-pill {
  display: inline-flex;
  align-items: center;
  min-height: 32px;
  padding: 0.34rem 0.8rem;
  border: 1px solid rgba(123, 95, 64, 0.14);
  border-radius: 999px;
  background: rgba(255, 252, 247, 0.84);
  color: var(--text-secondary);
  font-size: 0.82rem;
  font-weight: 700;
}

.analysis-pill.accent {
  background: rgba(186, 115, 73, 0.12);
  color: var(--accent-warm);
  border-color: rgba(186, 115, 73, 0.2);
}

.analysis-pill.positive {
  color: var(--accent-positive);
}

.analysis-pill.negative {
  color: var(--accent-danger);
}

.analysis-hero-main {
  display: grid;
  grid-template-columns: minmax(0, 1.1fr) minmax(280px, 0.9fr);
  gap: 1.2rem;
  align-items: start;
}

.analysis-title {
  margin: 0;
  color: var(--text-strong);
  font-family: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", Georgia, serif;
  font-size: clamp(2rem, 3.6vw, 3.1rem);
  line-height: 0.98;
  letter-spacing: -0.04em;
}

.analysis-subtitle {
  margin-top: 0.55rem;
  color: var(--text-secondary);
  font-size: 0.98rem;
  line-height: 1.7;
}

.analysis-quick-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 0.75rem;
}

.analysis-quick-item {
  min-width: 0;
  padding: 0.95rem 1rem;
  border-radius: 22px;
  border: 1px solid rgba(123, 95, 64, 0.1);
  background: rgba(255, 249, 241, 0.88);
}

.analysis-quick-label {
  display: block;
  color: var(--text-muted);
  font-size: 0.8rem;
  font-weight: 700;
}

.analysis-quick-value {
  display: block;
  min-width: 0;
  margin-top: 0.4rem;
  color: var(--text-strong);
  font-size: 1.12rem;
  font-weight: 700;
  line-height: 1.38;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.analysis-quick-meta {
  display: block;
  margin-top: 0.24rem;
  color: var(--text-secondary);
  font-size: 0.86rem;
  line-height: 1.45;
}

.analysis-market-strip {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.7rem;
  margin-top: 1rem;
}

.analysis-market-card {
  padding: 0.92rem 0.98rem;
  border-radius: 22px;
  border: 1px solid rgba(123, 95, 64, 0.1);
  background: rgba(255, 250, 243, 0.72);
}

.analysis-market-label {
  display: block;
  color: var(--text-secondary);
  font-size: 0.82rem;
  font-weight: 700;
}

.analysis-market-value {
  display: block;
  margin-top: 0.38rem;
  color: var(--text-strong);
  font-size: 1.08rem;
  font-weight: 700;
}

.analysis-market-delta {
  display: block;
  margin-top: 0.18rem;
  color: var(--text-muted);
  font-size: 0.86rem;
  font-weight: 600;
}

.analysis-market-delta.up {
  color: var(--accent-danger);
}

.analysis-market-delta.down {
  color: var(--accent-positive);
}

.analysis-nav-shell {
  display: flex;
  justify-content: center;
  align-items: center;
  width: 100%;
}

.analysis-nav-links {
  display: inline-flex;
  align-items: center;
  width: 100%;
  gap: 0.32rem;
  padding: 0.34rem;
  border: 1px solid var(--surface-line);
  border-radius: 24px;
  background: rgba(255, 249, 241, 0.9);
  box-shadow: var(--shadow-soft);
}

.analysis-nav-links-wide {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.analysis-nav-link {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  min-height: 46px;
  padding: 0.6rem 1.05rem;
  border-radius: 18px;
  color: var(--text-secondary);
  font-size: 0.92rem;
  font-weight: 700;
}

.analysis-nav-link:hover,
.analysis-nav-link:visited,
.analysis-nav-link:active {
  color: var(--text-strong);
}

.analysis-nav-link.is-active {
  background: rgba(255, 252, 247, 0.98);
  color: var(--text-strong);
  box-shadow: 0 8px 18px rgba(78, 54, 29, 0.08);
}

div[class*="st-key-single-stock-switch-popover"] .stPopover,
div[class*="st-key-multi-stock-edit-popover"] .stPopover {
  width: 100%;
}

div[class*="st-key-single-stock-switch-popover"] .stPopover > button,
div[class*="st-key-multi-stock-edit-popover"] .stPopover > button,
div[class*="st-key-multi-stock-remove-popover"] .stPopover > button,
div[class*="st-key-multi-stock-add-popover"] .stPopover > button {
  width: 100%;
  min-height: 48px;
  padding: 0.6rem 1.05rem;
  border: 1px solid var(--surface-line) !important;
  border-radius: 24px !important;
  background: rgba(255, 249, 241, 0.9) !important;
  color: var(--text-strong) !important;
  font-size: 0.92rem;
  font-weight: 700;
  box-shadow: var(--shadow-soft);
  justify-content: center;
}

div[class*="st-key-single-stock-switch-popover"] .stPopover > button:hover,
div[class*="st-key-multi-stock-edit-popover"] .stPopover > button:hover,
div[class*="st-key-multi-stock-remove-popover"] .stPopover > button:hover,
div[class*="st-key-multi-stock-add-popover"] .stPopover > button:hover {
  border-color: rgba(123, 95, 64, 0.24) !important;
  background: rgba(255, 252, 247, 0.98) !important;
}

div[class*="st-key-multi-stock-remove-popover"] .stPopover > button {
  border-color: rgba(179, 74, 69, 0.18) !important;
  background: rgba(255, 246, 244, 0.92) !important;
}

div[class*="st-key-multi-stock-remove-popover"] .stPopover > button:hover {
  border-color: rgba(179, 74, 69, 0.28) !important;
  background: rgba(255, 250, 247, 0.98) !important;
}

div[class*="st-key-multi-stock-add-popover"] .stPopover > button {
  border-color: rgba(78, 124, 89, 0.16) !important;
  background: rgba(246, 251, 247, 0.92) !important;
}

div[class*="st-key-multi-stock-add-popover"] .stPopover > button:hover {
  border-color: rgba(78, 124, 89, 0.26) !important;
  background: rgba(250, 253, 250, 0.98) !important;
}

div[class*="st-key-single-stock-switch-popover"] .stPopover > button p,
div[class*="st-key-multi-stock-edit-popover"] .stPopover > button p {
  margin: 0;
}

div[class*="st-key-single-stock-switch-popover"] .stPopover > button svg,
div[class*="st-key-multi-stock-edit-popover"] .stPopover > button svg {
  color: var(--text-secondary);
}

/* Single-stock analysis chrome follows the same borderless language as site nav. */
div[class*="st-key-single-stock-analysis-hero"] {
  padding: 0.72rem 1rem 0.7rem;
  border-radius: 24px;
}

div[class*="st-key-single-stock-hero-compact"] [data-testid="stHorizontalBlock"] {
  align-items: center;
}

div[class*="st-key-single-stock-hero-compact"] .analysis-title {
  font-size: clamp(1.35rem, 2.25vw, 2rem);
  line-height: 1.05;
}

div[class*="st-key-single-stock-hero-compact"] .analysis-subtitle {
  margin-top: 0.28rem;
  font-size: 0.86rem;
  line-height: 1.45;
}

div[class*="st-key-single-stock-analysis-hero"] div[class*="st-key-single-stock-header-range"] {
  margin: 0;
  padding: 0;
  border: 0;
  border-radius: 0;
  background: transparent;
}

div[class*="st-key-single-stock-analysis-hero"] div[class*="st-key-single-stock-header-range"] [data-testid="stCaptionContainer"] {
  margin-bottom: 0.18rem;
  font-size: 0.74rem;
}

div[class*="st-key-single-stock-analysis-hero"] div[class*="st-key-single-stock-header-range"] [data-testid="stDateInputField"] {
  min-height: 42px;
  border-radius: 16px !important;
  background: color-mix(in srgb, var(--surface-sheet) 82%, transparent) !important;
}

div[class*="st-key-single-stock-hero-toggle"] .stButton {
  display: flex;
  justify-content: flex-end;
}

div[class*="st-key-single-stock-hero-toggle"] .stButton button {
  width: auto;
  min-height: 2.4rem;
  padding: 0;
  border: 0 !important;
  border-radius: 0 !important;
  background: transparent !important;
  color: var(--text-secondary) !important;
  font-size: 0.82rem;
  font-weight: 580;
  box-shadow: none !important;
}

div[class*="st-key-single-stock-hero-toggle"] .stButton button:hover {
  color: var(--text-strong) !important;
  background: transparent !important;
}

.analysis-hero-details {
  margin-top: 0.72rem;
  padding-top: 0.85rem;
  border-top: 1px solid var(--surface-line);
  transform-origin: top center;
  animation: analysis-detail-slide-down 260ms cubic-bezier(0.22, 1, 0.36, 1) both;
}

.analysis-hero-details .analysis-hero-topline {
  margin-bottom: 0.75rem;
}

@keyframes analysis-detail-slide-down {
  from {
    opacity: 0;
    transform: translateY(-10px) scaleY(0.985);
  }
  to {
    opacity: 1;
    transform: translateY(0) scaleY(1);
  }
}

div[class*="st-key-single-stock-section-nav"] {
  padding: 0.18rem 0.2rem 0.28rem;
}

div[class*="st-key-single-stock-section-nav"] [data-testid="stHorizontalBlock"] {
  align-items: center;
}

div[class*="st-key-single-stock-section-nav"] div[class*="st-key-single_stock_analysis_section"] {
  width: 100%;
}

div[class*="st-key-single-stock-section-nav"] :is([data-testid="stSegmentedControl"], [data-testid="stButtonGroup"]) {
  width: 100%;
  padding: 0.16rem;
  border: 1px solid var(--surface-line);
  border-radius: 12px;
  background: color-mix(in srgb, var(--surface-frost) 82%, transparent);
  box-shadow: inset 0 1px 0 color-mix(in srgb, var(--surface-sheet) 72%, transparent);
}

div[class*="st-key-single-stock-section-nav"] [data-testid="stButtonGroup"] [role="radiogroup"] {
  width: 100%;
  gap: 0 !important;
}

div[class*="st-key-single-stock-section-nav"] :is([data-testid="stSegmentedControl"], [data-testid="stButtonGroup"]) button {
  flex: 1 1 0;
  min-height: 2.25rem;
  padding: 0.42rem 0.9rem;
  border: 0 !important;
  border-radius: 9px !important;
  background: transparent !important;
  color: var(--text-secondary) !important;
  font-size: 0.92rem;
  font-weight: 600;
  margin: 0 !important;
  box-shadow: none !important;
  justify-content: center;
}

div[class*="st-key-single-stock-section-nav"] :is([data-testid="stSegmentedControl"], [data-testid="stButtonGroup"]) button:hover {
  background: color-mix(in srgb, var(--surface-sheet) 54%, transparent) !important;
  color: var(--text-strong) !important;
}

div[class*="st-key-single-stock-section-nav"] :is([data-testid="stSegmentedControl"], [data-testid="stButtonGroup"]) button[aria-selected="true"],
div[class*="st-key-single-stock-section-nav"] :is([data-testid="stSegmentedControl"], [data-testid="stButtonGroup"]) button[aria-pressed="true"],
div[class*="st-key-single-stock-section-nav"] :is([data-testid="stSegmentedControl"], [data-testid="stButtonGroup"]) button[aria-checked="true"] {
  background: var(--surface-sheet) !important;
  color: var(--text-strong) !important;
  font-weight: 720;
  box-shadow: 0 5px 14px color-mix(in srgb, var(--text-strong) 8%, transparent) !important;
}

div[class*="st-key-single-stock-switch-popover"] {
  width: 100%;
  align-items: flex-end;
}

div[class*="st-key-single-stock-switch-popover"] > [data-testid="stLayoutWrapper"] {
  width: max-content;
  margin-left: auto;
}

div[class*="st-key-single-stock-switch-popover"] .stPopover {
  width: max-content;
  align-self: flex-end;
}

div[class*="st-key-single-stock-switch-popover"] .stPopover button {
  width: auto;
  min-height: 2.4rem;
  padding: 0;
  border: 0 !important;
  border-radius: 0 !important;
  background: transparent !important;
  color: var(--text-secondary) !important;
  font-weight: 560;
  box-shadow: none;
  justify-content: flex-end;
}

div[class*="st-key-single-stock-switch-popover"] .stPopover button:hover {
  border: 0 !important;
  background: transparent !important;
  color: var(--text-strong) !important;
}

@media (prefers-reduced-motion: reduce) {
  .analysis-hero-details {
    animation: none;
  }
}

.analysis-section-block {
  padding: 1.45rem 1.5rem;
  border: 1px solid var(--surface-line);
  border-radius: 30px;
  background: rgba(255, 251, 245, 0.92);
  box-shadow: var(--shadow-soft);
}

.analysis-section-header {
  margin-bottom: 1.05rem;
}

.analysis-section-title {
  margin: 0.3rem 0 0;
  color: var(--text-strong);
  font-size: 1.4rem;
  font-weight: 700;
}

.analysis-section-copy {
  margin: 0.4rem 0 0;
  color: var(--text-secondary);
  font-size: 0.95rem;
  line-height: 1.7;
}

.analysis-kv-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.75rem;
}

.analysis-kv-item {
  padding: 0.92rem 0.96rem;
  border-radius: 20px;
  background: rgba(248, 238, 224, 0.64);
  border: 1px solid rgba(123, 95, 64, 0.08);
}

.analysis-kv-label {
  display: block;
  color: var(--text-muted);
  font-size: 0.8rem;
  font-weight: 700;
}

.analysis-kv-value {
  display: block;
  margin-top: 0.34rem;
  color: var(--text-strong);
  font-size: 1.08rem;
  font-weight: 700;
}

.analysis-kv-meta {
  display: block;
  margin-top: 0.16rem;
  color: var(--text-secondary);
  font-size: 0.84rem;
  line-height: 1.45;
}

.analysis-chart-frame {
  padding: 1.1rem 1.15rem 0.8rem;
  border-radius: 26px;
  border: 1px solid rgba(123, 95, 64, 0.1);
  background: rgba(255, 252, 247, 0.94);
}

.analysis-chart-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.8rem;
  flex-wrap: wrap;
  margin-bottom: 0.7rem;
}

.analysis-chart-title {
  color: var(--text-strong);
  font-size: 1rem;
  font-weight: 700;
}

.analysis-chart-copy {
  color: var(--text-secondary);
  font-size: 0.88rem;
  line-height: 1.55;
}

.analysis-chart-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 0.42rem;
  margin-top: 0.75rem;
}

.analysis-chart-chip {
  display: inline-flex;
  align-items: center;
  min-height: 30px;
  padding: 0.3rem 0.68rem;
  border-radius: 999px;
  background: rgba(31, 25, 20, 0.06);
  color: var(--text-secondary);
  font-size: 0.8rem;
  font-weight: 700;
}

div[class*="st-key-single-stock-strategy-control-panel"],
div[class*="st-key-single-stock-strategy-result-board"] {
  padding: 1.25rem 1.2rem 1.15rem;
  border: 1px solid var(--surface-line);
  border-radius: 28px;
  background: rgba(255, 251, 245, 0.92);
  box-shadow: var(--shadow-soft);
}

div[class*="st-key-single-stock-strategy-result-board"] {
  background: rgba(255, 252, 247, 0.96);
}

@media (min-width: 881px) {
  div[class*="st-key-single-stock-strategy-control-panel"],
  div[class*="st-key-single-stock-strategy-result-board"] {
    flex: 0 0 clamp(44rem, calc(100vh - 5.5rem), 68rem) !important;
    height: clamp(44rem, calc(100vh - 5.5rem), 68rem);
    max-height: clamp(44rem, calc(100vh - 5.5rem), 68rem);
    min-height: 44rem;
    box-sizing: border-box;
    overflow-y: auto;
    overscroll-behavior: contain;
    scrollbar-gutter: stable;
  }
}

div[class*="st-key-model-evaluation-control-card"],
div[class*="st-key-model-evaluation-detail-section"] {
  padding: 1.35rem 1.4rem 1.22rem;
  border: 1px solid var(--surface-line);
  border-radius: 30px;
  background: rgba(255, 251, 245, 0.92);
  box-shadow: var(--shadow-soft);
}

div[class*="st-key-model-evaluation-tabs-shell"] {
  margin-top: 0.18rem;
}

div[class*="st-key-model-evaluation-tabs-shell"] [data-baseweb="tab-list"],
div[class*="st-key-model-evaluation-tabs-shell"] [role="tablist"] {
  padding: 0.28rem 0.4rem;
  gap: 0.32rem;
  margin-bottom: 0.4rem;
}

div[class*="st-key-model-evaluation-tabs-shell"] [data-baseweb="tab"],
div[class*="st-key-model-evaluation-tabs-shell"] button[role="tab"] {
  min-height: 44px;
  padding: 0.2rem 1rem 0.9rem;
  font-weight: 600;
  line-height: 1.35;
}

div[class*="st-key-model-evaluation-tabs-shell"] [data-baseweb="tab-panel"] {
  padding-top: 0.28rem;
}

div[class*="st-key-model-evaluation-summary-board"] {
  min-height: 520px;
  padding: 1.35rem 1.4rem 1.25rem;
  border: 1px solid var(--surface-line);
  border-radius: 32px;
  background: linear-gradient(180deg, rgba(255, 251, 245, 0.96), rgba(244, 231, 211, 0.94));
  box-shadow: var(--shadow-board);
}

.model-eval-rank-list {
  display: grid;
  gap: 0.72rem;
  margin-top: 1rem;
}

.model-eval-rank-item {
  display: flex;
  gap: 0.78rem;
  align-items: flex-start;
  padding: 0.86rem 0.92rem;
  border-radius: 22px;
  border: 1px solid rgba(123, 95, 64, 0.1);
  background: rgba(255, 249, 241, 0.86);
}

.model-eval-rank-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 44px;
  min-height: 30px;
  padding: 0.22rem 0.55rem;
  border-radius: 999px;
  background: rgba(31, 25, 20, 0.08);
  color: var(--text-strong);
  font-size: 0.8rem;
  font-weight: 700;
}

.model-eval-rank-copy {
  display: grid;
  gap: 0.18rem;
}

.model-eval-rank-title {
  color: var(--text-strong);
  font-size: 0.98rem;
  font-weight: 700;
}

.model-eval-rank-meta,
.model-eval-rank-empty {
  color: var(--text-secondary);
  font-size: 0.88rem;
  line-height: 1.58;
}

div[class*="st-key-single-stock-strategy-control-panel"] .stDivider,
div[class*="st-key-single-stock-strategy-result-board"] .stDivider {
  margin: 0.8rem 0 1rem;
}

div[class*="st-key-single-stock-strategy-control-panel"] [data-testid="stSegmentedControl"],
div[class*="st-key-single-stock-strategy-result-board"] [data-testid="stSegmentedControl"] {
  margin: 0.1rem 0 0.65rem;
}

.analysis-subsurface {
  padding: 1rem 1.05rem;
  border-radius: 24px;
  border: 1px solid rgba(123, 95, 64, 0.1);
  background: rgba(248, 238, 224, 0.46);
}

.analysis-subsurface + .analysis-subsurface {
  margin-top: 0.95rem;
}

.analysis-callout-title {
  margin: 0;
  color: var(--text-strong);
  font-size: 1.02rem;
  font-weight: 700;
}

.analysis-callout-copy {
  margin: 0.34rem 0 0;
  color: var(--text-secondary);
  font-size: 0.9rem;
  line-height: 1.62;
}

div[class*="st-key-single-stock-strategy-help-trigger"] {
  margin-top: 0.18rem;
}

div[class*="st-key-single-stock-strategy-help-trigger"] .stButton > button {
  min-height: auto;
  padding: 0.18rem 0;
  border: 0;
  background: transparent;
  color: var(--accent-warm);
  font-size: 0.9rem;
  font-weight: 800;
  box-shadow: none;
}

div[class*="st-key-single-stock-strategy-help-trigger"] .stButton > button:hover {
  color: var(--accent-primary);
  background: transparent;
  transform: none;
  box-shadow: none;
}

div[class*="st-key-single-stock-strategy-library-heading"] {
  width: max-content;
  max-width: 100%;
}

div[class*="st-key-single-stock-strategy-library-heading"] [data-testid="stMarkdownContainer"] p {
  margin: 0;
  color: var(--text-strong);
  font-size: 0.98rem;
  line-height: 1.4;
}

div[class*="st-key-single-stock-generate-actions"] [data-testid="stButton"] {
  margin-top: 0.8rem;
}

.strategy-result-empty {
  position: relative;
  min-height: 31rem;
  display: grid;
  place-items: center;
  margin-top: 0.8rem;
  overflow: hidden;
  color: var(--text-muted);
  background: transparent;
}

.strategy-result-empty-wordmark {
  width: 100%;
  color: color-mix(in srgb, var(--text-strong) 8%, transparent);
  font-family: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", "Songti SC", "STSong", Georgia, serif;
  font-size: clamp(2.6rem, 4vw, 4.4rem);
  font-weight: 760;
  line-height: 0.98;
  letter-spacing: -0.055em;
  text-align: center;
  white-space: nowrap;
  user-select: none;
}

.strategy-help-dialog {
  color: var(--text-primary);
}

.strategy-help-intro {
  margin: 0 0 1rem;
  color: var(--text-secondary);
  line-height: 1.68;
}

.strategy-help-steps {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.68rem;
  margin-bottom: 1.3rem;
}

.strategy-help-step {
  display: flex;
  gap: 0.68rem;
  padding: 0.8rem;
  border: 1px solid var(--surface-line);
  border-radius: 18px;
  background: rgba(248, 238, 224, 0.36);
}

.strategy-help-step > span {
  color: var(--accent-warm);
  font-size: 0.8rem;
  font-weight: 800;
}

.strategy-help-step strong,
.strategy-help-table strong {
  display: block;
  margin-bottom: 0.18rem;
  color: var(--text-strong);
}

.strategy-help-step p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 0.85rem;
  line-height: 1.55;
}

.strategy-help-dialog > h4 {
  margin: 0 0 0.68rem;
  color: var(--text-strong);
}

.strategy-help-table-wrap {
  overflow-x: auto;
}

.strategy-help-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.82rem;
  line-height: 1.48;
}

.strategy-help-table th,
.strategy-help-table td {
  padding: 0.68rem 0.72rem;
  border-top: 1px solid var(--surface-line);
  text-align: left;
  vertical-align: top;
}

.strategy-help-table th {
  min-width: 9rem;
  color: var(--text-strong);
}

@media (max-width: 880px) {
  .strategy-help-steps {
    grid-template-columns: 1fr;
  }

  .strategy-result-empty {
    min-height: 18rem;
  }
}

.status-note {
  display: flex;
  gap: 0.5rem;
  align-items: flex-start;
  margin-top: 0.5rem;
  color: var(--text-muted);
  font-size: 0.9rem;
  line-height: 1.58;
}

.status-note::before {
  content: "";
  width: 0.42rem;
  height: 0.42rem;
  margin-top: 0.45rem;
  border-radius: 999px;
  background: rgba(154, 130, 104, 0.72);
  flex: 0 0 auto;
}

.status-note.warning {
  color: var(--accent-warning);
}

.status-note.warning::before {
  background: rgba(164, 100, 41, 0.66);
}

.status-note.error {
  color: var(--accent-danger);
}

.status-note.error::before {
  background: rgba(179, 74, 69, 0.72);
}

.status-note.positive {
  color: var(--accent-positive);
}

.status-note.positive::before {
  background: rgba(78, 124, 89, 0.72);
}

div[class*="st-key-single-recommend-scroll"],
div[class*="st-key-multi-recommend-scroll"] {
  max-height: 22rem;
  overflow-y: auto;
  padding-right: 0.2rem;
}

div[class*="st-key-single-recommend-scroll"] {
  max-height: 14rem;
}

@media (min-width: 881px) {
  div[class*="st-key-single-recommend-scroll"],
  div[class*="st-key-multi-recommend-scroll"] {
    max-height: none;
  }
}

div[class*="st-key-single-recommend-scroll"] [data-testid="stHorizontalBlock"],
div[class*="st-key-multi-recommend-scroll"] [data-testid="stHorizontalBlock"],
div[class*="st-key-multi-selected-symbols"] [data-testid="stHorizontalBlock"] {
  align-items: center;
}

div[class*="st-key-single-recommend-scroll"] .stButton,
div[class*="st-key-multi-recommend-scroll"] .stButton,
div[class*="st-key-multi-selected-symbols"] .stButton {
  display: flex;
  align-items: center;
  height: 100%;
}

div[class*="st-key-single-recommend-scroll"] .stButton > button,
div[class*="st-key-multi-recommend-scroll"] .stButton > button,
div[class*="st-key-multi-selected-symbols"] .stButton > button {
  min-height: 34px;
  padding: 0.4rem 0.62rem;
  font-size: 0.78rem;
}

.stButton > button,
.stDownloadButton > button,
.stFormSubmitButton > button {
  min-height: 42px;
  padding: 0.64rem 0.96rem;
  border: 1px solid var(--surface-line-strong);
  border-radius: 999px;
  background: rgba(255, 251, 245, 0.84);
  color: var(--text-strong);
  font-weight: 700;
  box-shadow: none;
  transition: transform 0.15s ease, background 0.15s ease, border-color 0.15s ease;
}

.stButton > button:hover,
.stDownloadButton > button:hover,
.stFormSubmitButton > button:hover {
  transform: translateY(-1px);
  background: rgba(255, 252, 247, 0.98);
  border-color: rgba(123, 95, 64, 0.28);
}

.stButton > button[kind="primary"],
.stDownloadButton > button[kind="primary"],
.stFormSubmitButton > button[kind="primary"] {
  background: var(--accent-primary);
  color: var(--text-inverse);
  border-color: transparent;
}

[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea,
[data-testid="stNumberInput"] input,
div[data-baseweb="select"] > div,
[data-testid="stDateInputField"],
[data-testid="stFileUploaderDropzone"] {
  border-radius: 18px !important;
  border-color: rgba(123, 95, 64, 0.16) !important;
  background: rgba(255, 251, 245, 0.76) !important;
  color: var(--text-primary) !important;
}

[data-testid="stFileUploaderDropzone"] {
  border-style: dashed !important;
}

[data-testid="stSegmentedControl"] {
  padding: 0.24rem;
  border: 1px solid var(--surface-line);
  border-radius: 999px;
  background: rgba(255, 250, 242, 0.68);
}

[data-testid="stSegmentedControl"] button {
  min-height: 38px;
  border-radius: 999px !important;
  color: var(--text-secondary) !important;
}

[data-testid="stSegmentedControl"] button[aria-selected="true"],
[data-testid="stSegmentedControl"] button[aria-pressed="true"] {
  background: var(--accent-primary) !important;
  color: var(--text-inverse) !important;
}

div[class*="st-key-single-action-card"] [role="radio"][aria-checked="true"],
div[class*="st-key-multi-action-card"] [role="radio"][aria-checked="true"] {
  border-color: var(--accent-primary) !important;
  background: var(--accent-primary-soft) !important;
  box-shadow: none !important;
}

div[class*="st-key-single-action-card"] [role="radio"][aria-checked="true"] p,
div[class*="st-key-multi-action-card"] [role="radio"][aria-checked="true"] p {
  color: var(--text-strong) !important;
}

[data-testid="stRadio"] > div {
  gap: 0.55rem;
}

[data-testid="stRadio"] label {
  padding: 0.82rem 0.9rem;
  border: 1px solid var(--surface-line);
  border-radius: 18px;
  background: rgba(255, 251, 245, 0.68);
}

[data-testid="stRadio"] label:hover {
  border-color: rgba(123, 95, 64, 0.24);
}

[data-testid="stCaptionContainer"],
.stCaption,
.stMarkdown small,
.stMarkdown a {
  color: var(--text-muted);
}

@media (max-width: 1100px) {
  .home-showcase {
    margin-top: 0;
  }

  div[class*="st-key-model-evaluation-summary-board"] {
    min-height: 620px;
  }
}

@media (max-width: 880px) {
  .site-header {
    grid-template-columns: minmax(0, 1fr) auto;
    grid-template-areas:
      "brand utility"
      "nav nav";
    gap: 0.2rem 1rem;
    padding-bottom: 0.35rem;
  }

  .site-brand-wrap {
    grid-area: brand;
  }

  .site-nav {
    grid-area: nav;
    justify-content: flex-start;
    width: 100%;
    overflow-x: auto;
    scrollbar-width: none;
  }

  .site-nav::-webkit-scrollbar {
    display: none;
  }

  .site-utility-nav {
    grid-area: utility;
  }

  .snapshot-grid {
    grid-template-columns: 1fr;
  }

  .home-showcase-grid {
    grid-template-columns: 1fr;
  }

  .showcase-board,
  div[class*="st-key-single-showcase-board"],
  div[class*="st-key-multi-showcase-board"],
  div[class*="st-key-model-evaluation-summary-board"] {
    min-height: auto;
  }

  .analysis-hero-main,
  .analysis-quick-grid,
  .analysis-market-strip,
  .analysis-kv-grid {
    grid-template-columns: 1fr;
  }

  div[class*="st-key-single-entry-split"] > div[data-testid="stElementContainer"] > div[data-testid="stHorizontalBlock"],
  div[class*="st-key-multi-entry-split"] > div[data-testid="stElementContainer"] > div[data-testid="stHorizontalBlock"] {
    flex-direction: column;
    flex-wrap: nowrap;
  }

  div[class*="st-key-single-entry-split"] > div[data-testid="stElementContainer"] > div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"],
  div[class*="st-key-single-entry-split"] > div[data-testid="stElementContainer"] > div[data-testid="stHorizontalBlock"] > div[data-testid="column"],
  div[class*="st-key-multi-entry-split"] > div[data-testid="stElementContainer"] > div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"],
  div[class*="st-key-multi-entry-split"] > div[data-testid="stElementContainer"] > div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
    width: 100% !important;
    min-width: 100% !important;
    flex: 1 1 100% !important;
  }

  .board-main-sheet,
  .floating-sheet {
    position: static;
    width: auto !important;
    margin-top: 0.85rem;
  }
}

@media (max-width: 640px) {
  .entry-title {
    font-size: 2.18rem;
  }

  div[class*="st-key-single-market-heading-row"] [data-testid="stHorizontalBlock"],
  div[class*="st-key-multi-market-heading-row"] [data-testid="stHorizontalBlock"] {
    flex-direction: column;
    flex-wrap: nowrap;
  }

  div[class*="st-key-single-market-heading-row"] [data-testid="stHorizontalBlock"] > div[data-testid="stColumn"],
  div[class*="st-key-single-market-heading-row"] [data-testid="stHorizontalBlock"] > div[data-testid="column"],
  div[class*="st-key-multi-market-heading-row"] [data-testid="stHorizontalBlock"] > div[data-testid="stColumn"],
  div[class*="st-key-multi-market-heading-row"] [data-testid="stHorizontalBlock"] > div[data-testid="column"] {
    width: 100% !important;
    min-width: 100% !important;
    flex: 1 1 100% !important;
  }

  div[class*="st-key-single-refresh-market-context"] .stButton > button,
  div[class*="st-key-multi-refresh-market-context"] .stButton > button {
    width: 100%;
  }

  .site-nav {
    width: 100%;
    justify-content: flex-start;
    gap: 1.25rem;
  }

  .site-brand {
    font-size: 1.42rem;
  }

  .site-utility-nav {
    gap: 0.65rem;
  }

  .site-utility-link {
    font-size: 0.74rem;
  }

  .site-language-switch {
    gap: 0.42rem;
  }

  .home-market-stage {
    min-height: clamp(900px, calc(100vh - 7.2rem), 980px);
    margin-top: 0;
  }

  .market-identity {
    top: clamp(4rem, 8vh, 5.6rem);
    width: 91vw;
  }

  .market-platform-title {
    max-width: 92vw;
    font-size: clamp(2.1rem, 9.2vw, 3.05rem);
    line-height: 1.03;
    letter-spacing: -0.04em;
  }

  .market-news-ticker {
    width: 88vw;
    height: 1.7rem;
    margin-top: 0.85rem;
  }

  .market-news-item {
    font-size: 0.78rem;
    line-height: 1.7rem;
  }

  .market-stock-cloud {
    top: 12rem;
    width: 94vw;
    height: 176px;
  }

  .market-stock-focus {
    top: 48%;
    width: 66vw;
  }

  .market-stock-eyebrow {
    font-size: 0.55rem;
  }

  .market-stock-focus-line {
    gap: 0.45rem;
  }

  .market-stock-company {
    font-size: clamp(1.35rem, 6.2vw, 1.8rem);
  }

  .market-stock-focus-line b {
    font-size: 0.7rem;
  }

  .market-stock-focus-line span {
    font-size: 0.58rem;
  }

  .market-candles {
    height: 58px;
    margin-top: 0.38rem;
  }

  .market-stock-orbit strong {
    font-size: 0.72rem;
  }

  .market-stock-orbit small {
    display: none;
  }

  .market-stock-orbit span {
    font-size: 0.56rem;
  }

  .market-stock-orbit.slot-1 { top: 16%; left: 0; }
  .market-stock-orbit.slot-2 { top: 12%; right: 0; }
  .market-stock-orbit.slot-3,
  .market-stock-orbit.slot-4 { display: none; }

  div.st-key-home-stage-shell div.st-key-home-stock-controls {
    top: 23rem;
    width: 220px;
  }

  .market-lens {
    bottom: 2.8rem;
    width: 90vw;
    height: 445px;
  }

  .market-lens-scene {
    bottom: 3rem;
    justify-content: flex-start;
    padding-top: 0.5rem;
  }

  .market-lens-heading {
    display: block;
    margin-bottom: 1.35rem;
  }

  .market-lens-heading > span,
  .market-lens-heading > strong {
    display: block;
    text-align: left;
  }

  .market-lens-heading > strong {
    margin-top: 0.45rem;
    font-size: 0.84rem;
  }

  .market-index-strip {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0.25rem 0;
  }

  .market-index-item {
    padding: 0.4rem 0.75rem 0.75rem;
  }

  .market-index-item + .market-index-item::before {
    display: none;
  }

  .market-index-item:nth-child(even)::before {
    content: "";
    position: absolute;
    top: 8%;
    bottom: 7%;
    left: 0;
    display: block;
    width: 1px;
    background: linear-gradient(180deg, transparent, var(--surface-line-strong), transparent);
  }

  .market-index-item strong {
    font-size: 0.84rem;
  }

  .market-item-quote {
    font-size: 0.98rem;
  }

  .market-leader-list {
    grid-template-columns: 1fr;
  }

  .market-leader-item {
    grid-template-columns: 1.7rem minmax(0, 1fr) auto auto;
    gap: 0.55rem;
    padding: 0.72rem 0.2rem;
  }

  .market-leader-region {
    display: none;
  }

  .market-leader-name {
    font-size: 0.74rem;
  }

  .market-leader-name strong {
    font-size: 0.86rem;
  }

  .market-temperature-body {
    display: block;
  }

  .market-temperature-statement strong {
    font-size: clamp(2.35rem, 12vw, 3.4rem);
  }

  .market-temperature-statement span {
    display: block;
    max-width: 85vw;
    margin-top: 0.65rem;
  }

  .market-temperature-metrics {
    margin-top: 2.25rem;
  }

  .market-temperature-metrics > div {
    padding-left: 0.75rem;
  }

  .market-lens-source {
    max-width: calc(100% - 6rem);
    font-size: 0.58rem;
  }

  .market-lens-progress {
    bottom: 1.7rem;
  }

  .market-lens-progress i {
    width: 1.25rem;
  }

  .cta-row {
    width: 100%;
  }

  .cta-link {
    width: 100%;
  }

  .entry-path-step {
    width: 100%;
  }
}

@media (prefers-reduced-motion: reduce) {
  .market-stock-cloud,
  .market-lens-scene,
  .market-lens-progress i::after {
    animation: none;
  }

  .market-lens-scene {
    display: none;
    opacity: 0;
    transform: none;
  }

  .market-lens-scene:first-child {
    display: flex;
    opacity: 1;
  }

  .market-lens-progress i:first-child::after {
    opacity: 1;
    transform: scaleX(1);
  }

  .market-news-item {
    display: none;
    animation: none;
    opacity: 0;
    transform: none;
  }

  .market-news-item:first-child {
    display: block;
    opacity: 1;
  }
}
        """
    style_markup = style_markup.replace("__ROOT_TOKENS__", theme_styles["root_tokens"])
    style_markup = style_markup.replace("__APP_BACKGROUND__", theme_styles["app_background"])
    style_markup = style_markup.replace("__SIDEBAR_BACKGROUND__", theme_styles["sidebar_background"])
    style_markup = style_markup.replace("__ACTIVE_TAB_SHADOW__", theme_styles["active_tab_shadow"])
    return style_markup


_STYLE_BUNDLE_NAMES = ("base", "home", "entry", "analysis", "report")
_STYLE_BUNDLE_HINTS = {
    "home": (
        ".home-",
        ".market-",
        "st-key-home-",
        "keyframes market-",
    ),
    "entry": (
        ".action-card",
        ".board-",
        ".cta-",
        ".entry-",
        ".floating-sheet",
        ".hero-",
        ".page-kicker",
        ".plain-helper",
        ".recommend-",
        ".section-divider",
        ".selection-",
        ".showcase-",
        ".snapshot-",
        ".source-note",
        ".support-",
        ".surface-",
        ".upload-row",
        "st-key-multi-action-card",
        "st-key-multi-csv-requirements",
        "st-key-multi-entry-split",
        "st-key-multi-market-heading-row",
        "st-key-multi-recommend",
        "st-key-multi-refresh-market-context",
        "st-key-multi-selected-symbols",
        "st-key-multi-showcase-board",
        "st-key-multi-stock-add-list",
        "st-key-multi-stock-remove-list",
        "st-key-multi-selected-stock-popover",
        "st-key-single-action-card",
        "st-key-single-csv-requirements",
        "st-key-single-entry-split",
        "st-key-single-market-heading-row",
        "st-key-single-recommend",
        "st-key-single-refresh-market-context",
        "st-key-single-showcase-board",
    ),
    "analysis": (
        ".analysis-",
        ".board-flow-row",
        ".board-micro-",
        ".model-eval-",
        ".recommend-row",
        ".surface-",
        "st-key-model-evaluation",
        "st-key-multi-stock-analysis",
        "st-key-multi-stock-basic",
        "st-key-multi-stock-chart",
        "st-key-multi-stock-edit-popover",
        "st-key-multi-stock-header",
        "st-key-multi-stock-strategy",
        "st-key-single-stock-analysis",
        "st-key-single-stock-basic",
        "st-key-single-stock-chart",
        "st-key-single-stock-header",
        "st-key-single-stock-section-nav",
        "st-key-single-stock-strategy",
        "st-key-single-stock-switch-popover",
    ),
    "report": (
        ".native-report-",
        ".report-",
        "st-key-final-report-",
        "keyframes report-",
    ),
}


def _find_css_block_end(source: str, opening_brace: int) -> int:
    """Return the matching closing brace while respecting CSS strings/comments."""
    depth = 1
    index = opening_brace + 1
    quote = ""
    escaped = False
    in_comment = False
    while index < len(source):
        char = source[index]
        next_char = source[index + 1] if index + 1 < len(source) else ""
        if in_comment:
            if char == "*" and next_char == "/":
                in_comment = False
                index += 2
                continue
        elif quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
        elif char == "/" and next_char == "*":
            in_comment = True
            index += 2
            continue
        elif char in {'"', "'"}:
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    raise ValueError("Unbalanced CSS block in theme source")


def _iter_css_rules(source: str):
    """Yield top-level ``(prelude, body)`` CSS rules in source order."""
    cursor = 0
    while cursor < len(source):
        comment_start = source.find("/*", cursor)
        opening_brace = source.find("{", cursor)
        if comment_start >= 0 and (opening_brace < 0 or comment_start < opening_brace):
            comment_end = source.find("*/", comment_start + 2)
            if comment_end < 0:
                raise ValueError("Unbalanced CSS comment in theme source")
            cursor = comment_end + 2
            continue
        if opening_brace < 0:
            break
        prelude = source[cursor:opening_brace].strip()
        if not prelude:
            cursor = opening_brace + 1
            continue
        closing_brace = _find_css_block_end(source, opening_brace)
        yield prelude, source[opening_brace + 1 : closing_brace]
        cursor = closing_brace + 1


def _rule_bundle_names(prelude: str) -> tuple[str, ...]:
    normalized = prelude.lower()
    matches = tuple(
        bundle
        for bundle, hints in _STYLE_BUNDLE_HINTS.items()
        if any(hint in normalized for hint in hints)
    )
    return matches or ("base",)


def _append_compiled_rule(
    bundles: dict[str, list[str]],
    prelude: str,
    body: str,
) -> None:
    normalized = prelude.lstrip().lower()
    if normalized.startswith(("@media", "@supports", "@container", "@layer")):
        nested = {name: [] for name in _STYLE_BUNDLE_NAMES}
        for nested_prelude, nested_body in _iter_css_rules(body):
            _append_compiled_rule(nested, nested_prelude, nested_body)
        for bundle, rules in nested.items():
            if rules:
                bundles[bundle].append(f"{prelude} {{\n{''.join(rules)}\n}}\n")
        return

    rule = f"{prelude} {{\n{body}\n}}\n"
    for bundle in _rule_bundle_names(prelude):
        bundles[bundle].append(rule)


@lru_cache(maxsize=2)
def _compile_style_bundles(style_source: str) -> dict[str, str]:
    bundles = {name: [] for name in _STYLE_BUNDLE_NAMES}
    for prelude, body in _iter_css_rules(style_source):
        _append_compiled_rule(bundles, prelude, body)
    return {name: "".join(rules).strip() for name, rules in bundles.items()}


def get_style_bundle_css(bundle: str) -> str:
    """Return compiled CSS for one route bundle (used by injection and QA)."""
    if bundle not in _STYLE_BUNDLE_NAMES:
        raise ValueError(f"Unknown style bundle: {bundle}")
    return _compile_style_bundles(_build_style_source())[bundle]


def _inject_style_bundle(bundle: str) -> None:
    render_html(f"<style>\n{get_style_bundle_css(bundle)}\n</style>", localize=False)


def inject_base_styles() -> None:
    """Inject tokens, site shell, shared controls, and responsive foundations."""
    ensure_ui_preferences()
    install_streamlit_localizers()
    _inject_style_bundle("base")


def inject_home_styles() -> None:
    """Inject the homepage market-stage and motion rules."""
    _inject_style_bundle("home")


def inject_entry_styles() -> None:
    """Inject single/multi-stock entry-page rules."""
    _inject_style_bundle("entry")


def inject_analysis_styles() -> None:
    """Inject single/multi-stock and model-evaluation analysis rules."""
    _inject_style_bundle("analysis")


def inject_report_styles() -> None:
    """Inject native final-report reader rules."""
    _inject_style_bundle("report")


def inject_global_styles() -> None:
    """Compatibility entry point that injects the complete legacy stylesheet."""
    ensure_ui_preferences()
    install_streamlit_localizers()
    render_html(f"<style>\n{_build_style_source()}\n</style>", localize=False)


def render_route_nav(current: str) -> None:
    """action.render_site_nav"""
    ensure_ui_preferences()
    active_language = get_ui_language()
    nav_items = [
        ("home", t(tr("nav.home"), "Home"), route_href("")),
        ("single", t(tr("analysis.singleInstrument"), "Single Stock"), route_href("stock-analysis")),
        ("multi", t(tr("analysis.multiStock"), "Multi Stock"), route_href("stocks-analysis")),
        ("doc", t("帮助", "Help"), route_href("final-report")),
    ]
    links_html = "".join(
        (
            f"<a class='site-link {'active' if key == current else ''}' href='{href}' "
            f"{'aria-current=\"page\"' if key == current else ''}>{label}</a>"
        )
        for key, label, href in nav_items
    )
    current_path = {
        "home": "",
        "single": "stock-analysis",
        "multi": "stocks-analysis",
        "model-evaluation": "model-evaluation",
        "experiment-monitor": "experiment-monitor",
        "doc": "final-report",
    }.get(current, "")
    preserved_query: dict[str, str] = {}
    if current == "doc":
        try:
            section = str(st.query_params.get("section", ""))
        except (AttributeError, KeyError, TypeError):
            section = ""
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", section):
            preserved_query["section"] = section
    language_links = "".join(
        (
            f"<a class='site-language-link {'active' if code == active_language else ''}' "
            f"href='{html.escape(route_href(current_path, language=code, query=preserved_query), quote=True)}' "
            f"lang='{'zh-CN' if code == 'zh' else 'en'}' "
            f"aria-label='{label}' title='{label}'>{short_label}</a>"
        )
        for code, short_label, label in (
            ("zh", "中", "切换为中文"),
            ("en", "EN", "Switch to English"),
        )
    )
    evidence_href = route_href("model-evaluation")
    evidence_label = t("浏览研究证据", "Browse evidence")
    with st.container(key=f"route-header-shell-{current}"):
        render_html(
            f"""
<header class="site-header">
  <div class="site-brand-wrap">
    <a class="site-brand" href="{route_href('')}">Strategy Lab</a>
  </div>
  <nav class="site-nav" aria-label="{t('主导航', 'Primary navigation')}">{links_html}</nav>
  <div class="site-utility-nav">
    <a class="site-utility-link {'active' if current == 'model-evaluation' else ''}"
       href="{evidence_href}" {'aria-current="page"' if current == 'model-evaluation' else ''}>{evidence_label}</a>
    <span class="site-language-switch" aria-label="{t('语言切换', 'Language')}">{language_links}</span>
  </div>
</header>
            """
        )


def render_status_note(message: str, tone: str = "info") -> None:
    """ui.render_inline_status"""
    tone_class = tone if tone in {"info", "positive", "warning", "error"} else "info"
    st.markdown(
        f"<div class='status-note {tone_class}'>{html.escape(str(translate_text(message)))}</div>",
        unsafe_allow_html=True,
    )
