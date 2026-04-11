"""
共享前端主题层
==============
为 W6 首页、入口页和路由壳层提供暖米白官网式样式。
"""

from __future__ import annotations

import html
from datetime import date as _date, datetime as _datetime
from functools import wraps
from textwrap import dedent

import streamlit as st
from ui.i18n import tr


BASE_ROUTE_PATH = "/strategy"
UI_LANGUAGE_STATE_KEY = "ui_language"
UI_THEME_STATE_KEY = "ui_theme"



def ensure_ui_preferences() -> None:
    st.session_state.setdefault(UI_LANGUAGE_STATE_KEY, "en")
    st.session_state.setdefault(UI_THEME_STATE_KEY, "light")


def get_ui_language() -> str:
    ensure_ui_preferences()
    st.session_state[UI_LANGUAGE_STATE_KEY] = "en"
    return "en"


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

    if getattr(fig.layout, "title", None) is not None:
        fig.layout.title.text = translate_text(fig.layout.title.text)
        fig.layout.title.font = {
            **(fig.layout.title.font.to_plotly_json() if fig.layout.title.font else {}),
            "color": tokens["font_color"],
            "family": tokens["font_family"],
        }

    if getattr(fig.layout, "legend", None) is not None and getattr(fig.layout.legend, "title", None) is not None:
        fig.layout.legend.title.text = translate_text(fig.layout.legend.title.text)

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


def route_href(url_path: str = "") -> str:
    """system.routing.buildPath"""
    normalized = str(url_path or "").strip().strip("/")
    base = f"{BASE_ROUTE_PATH}/{normalized}" if normalized else BASE_ROUTE_PATH
    return base

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


def inject_global_styles() -> None:
    """theme.injectGlobalStyles"""
    ensure_ui_preferences()
    install_streamlit_localizers()
    theme_styles = _get_ui_theme_style_values()
    style_markup = """
<style>
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
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1.3rem;
  margin: 0 auto 2rem;
  padding: 0.35rem 0 0.8rem;
}

div[class*="st-key-route-header-shell-"] {
  margin: 0 auto 2rem;
  padding: 0.35rem 0 0.8rem;
}

div[class*="st-key-route-header-shell-"] > div[data-testid="stHorizontalBlock"] {
  align-items: center;
  gap: clamp(0.9rem, 2vw, 1.45rem);
}

div[class*="st-key-route-header-brand-"],
div[class*="st-key-route-header-preferences-"],
div[class*="st-key-route-header-nav-"] {
  min-width: 0;
}

div[class*="st-key-route-header-brand-"] .site-brand-wrap {
  min-height: 3rem;
}

div[class*="st-key-route-header-preferences-"] {
  display: flex;
  align-items: center;
  max-width: 392px;
  margin: 0 0 0 auto;
}

div[class*="st-key-route-header-preferences-"] > div[data-testid="stHorizontalBlock"] {
  align-items: center;
}

div[class*="st-key-route-header-preferences-"] > div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
  display: flex;
  align-items: center;
}

div[class*="st-key-route-header-preferences-"] [data-testid="stSegmentedControl"] {
  width: 100%;
  margin: 0;
}

div[class*="st-key-route-header-nav-"] {
  display: flex;
  justify-content: flex-end;
}

div[class*="st-key-route-header-nav-"] .site-nav {
  margin-left: auto;
}

.site-brand-wrap {
  display: flex;
  align-items: center;
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
  display: inline-flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.18rem;
  padding: 0.3rem;
  border: 1px solid var(--surface-line);
  border-radius: 999px;
  background: rgba(255, 249, 241, 0.78);
  box-shadow: var(--shadow-soft);
}

.site-link {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 40px;
  padding: 0.58rem 0.98rem;
  border-radius: 999px;
  color: var(--text-secondary);
  font-size: 0.95rem;
  font-weight: 600;
  transition: color 0.15s ease, background 0.15s ease, box-shadow 0.15s ease;
}

.site-link:hover,
.site-link.active {
  color: var(--text-strong);
  background: rgba(255, 253, 248, 0.98);
  box-shadow: 0 8px 18px rgba(78, 54, 29, 0.08);
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

.hero-shell {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(430px, 0.95fr);
  align-items: start;
  gap: clamp(2rem, 4vw, 3.8rem);
  margin-bottom: 3rem;
  padding-top: clamp(0.8rem, 2vw, 2rem);
}

.hero-copy-column {
  padding-top: clamp(0.2rem, 1vw, 1rem);
}

.hero-title,
.entry-title {
  margin: 1rem 0 0.85rem;
  color: var(--text-strong);
  font-family: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", Georgia, serif;
  line-height: 0.96;
  letter-spacing: -0.05em;
}

.hero-title {
  font-size: clamp(3.2rem, 5.8vw, 5.5rem);
}

.entry-title {
  font-size: clamp(2.3rem, 4.6vw, 3.4rem);
}

.hero-copy,
.entry-copy {
  max-width: 560px;
  margin: 0;
  color: var(--text-secondary);
  font-size: 1.05rem;
  line-height: 1.78;
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
  min-height: 34px;
  padding: 0.38rem 0.8rem;
  border-radius: 999px;
  background: var(--accent-primary-soft);
  color: var(--text-primary);
  font-size: 0.84rem;
  font-weight: 600;
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

.support-columns {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 1.6rem;
}

.support-block {
  padding-top: 1rem;
  border-top: 1px solid var(--surface-line);
}

.support-block h3 {
  margin: 0 0 0.35rem;
  color: var(--text-strong);
  font-size: 1rem;
  font-weight: 700;
}

.support-block p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 0.94rem;
  line-height: 1.7;
}

.support-cta-row {
  display: flex;
  flex-wrap: wrap;
  margin-top: 0.95rem;
}

.support-cta-row .cta-link {
  width: auto;
}

div[class*="st-key-single-action-card"],
div[class*="st-key-multi-action-card"] {
  padding: 1.4rem 1.45rem 1.3rem;
  border: 1px solid var(--surface-line);
  border-radius: 28px;
  background: var(--surface-sheet);
  box-shadow: var(--shadow-soft);
}

div[class*="st-key-single-showcase-board"],
div[class*="st-key-multi-showcase-board"] {
  min-height: 720px;
  padding: 1.35rem 1.4rem 1.25rem;
  border: 1px solid var(--surface-line);
  border-radius: 32px;
  background: linear-gradient(180deg, rgba(255, 251, 245, 0.96), rgba(244, 231, 211, 0.94));
  box-shadow: var(--shadow-board);
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
  .hero-shell {
    grid-template-columns: 1fr;
    gap: 2rem;
  }

  .home-showcase {
    margin-top: 0;
  }

  div[class*="st-key-single-showcase-board"],
  div[class*="st-key-multi-showcase-board"],
  div[class*="st-key-model-evaluation-summary-board"] {
    min-height: 620px;
  }
}

@media (max-width: 880px) {
  .site-header,
  div[class*="st-key-route-header-shell-"] > div[data-testid="stHorizontalBlock"] {
    flex-direction: column;
    align-items: flex-start;
    gap: 0.75rem;
  }

  div[class*="st-key-route-header-shell-"] > div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
    width: 100% !important;
    min-width: 100% !important;
    flex: 1 1 100% !important;
  }

  div[class*="st-key-route-header-preferences-"] {
    max-width: none;
    margin: 0;
  }

  div[class*="st-key-route-header-nav-"] {
    justify-content: flex-start;
  }

  div[class*="st-key-route-header-nav-"] .site-nav {
    margin-left: 0;
  }

  .support-columns,
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

  .board-main-sheet,
  .floating-sheet {
    position: static;
    width: auto !important;
    margin-top: 0.85rem;
  }
}

@media (max-width: 640px) {
  .hero-title {
    font-size: 2.95rem;
  }

  .entry-title {
    font-size: 2.18rem;
  }

  .site-nav {
    width: 100%;
    justify-content: space-between;
  }

  div[class*="st-key-route-header-preferences-"] > div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
    width: 100% !important;
    min-width: 100% !important;
    flex: 1 1 100% !important;
  }

  .cta-row {
    width: 100%;
  }

  .cta-link {
    width: 100%;
  }
}
</style>
        """
    style_markup = style_markup.replace("__ROOT_TOKENS__", theme_styles["root_tokens"])
    style_markup = style_markup.replace("__APP_BACKGROUND__", theme_styles["app_background"])
    style_markup = style_markup.replace("__SIDEBAR_BACKGROUND__", theme_styles["sidebar_background"])
    style_markup = style_markup.replace("__ACTIVE_TAB_SHADOW__", theme_styles["active_tab_shadow"])
    render_html(style_markup, localize=False)


def render_route_nav(current: str) -> None:
    """action.render_site_nav"""
    ensure_ui_preferences()
    nav_items = [
        ("home", t(tr("nav.home"), "Home"), route_href("")),
        ("single", t(tr("analysis.singleInstrument"), "Single Stock"), route_href("stock-analysis")),
        ("multi", t(tr("analysis.multiStock"), "Multi Stock"), route_href("stocks-analysis")),
    ]
    links_html = "".join(
        f"<a class='site-link {'active' if key == current else ''}' href='{href}'>{label}</a>"
        for key, label, href in nav_items
    )
    with st.container(key=f"route-header-shell-{current}"):
        brand_col, nav_col = st.columns([0.92, 1.08], gap="large", vertical_alignment="center")

        with brand_col:
            with st.container(key=f"route-header-brand-{current}"):
                render_html(
                    f"""
<div class="site-brand-wrap">
  <span class="site-brand-mark"></span>
  <div class="site-brand-copy">
    <a class="site-brand" href="{route_href('')}">Strategy Lab</a>
    <div class="site-brand-subtitle">{t("\u5355\u80a1\u7814\u7a76\u4e0e\u591a\u80a1\u6bd4\u8f83\u7684\u8def\u7531\u5f0f\u7b56\u7565\u7ad9\u70b9\u3002", "A route-based strategy site for single-stock research and multi-stock comparison.")}</div>
  </div>
</div>
                    """
                )

        with nav_col:
            with st.container(key=f"route-header-nav-{current}"):
                render_html(f"<nav class='site-nav'>{links_html}</nav>")


def render_status_note(message: str, tone: str = "info") -> None:
    """ui.render_inline_status"""
    tone_class = tone if tone in {"info", "positive", "warning", "error"} else "info"
    st.markdown(
        f"<div class='status-note {tone_class}'>{html.escape(str(translate_text(message)))}</div>",
        unsafe_allow_html=True,
    )
