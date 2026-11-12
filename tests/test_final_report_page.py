import re
from html import unescape
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
import ui.final_report as final_report
import ui.theme as theme
from ui.final_report import (
    build_report_navigation,
    build_report_reader,
    extract_embeddable_report,
    filter_report_sections,
    get_report_path,
    split_report_intro,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_report_editions_keep_the_full_archived_content() -> None:
    expected_titles = {
        "zh": "量化策略分析WebApp",
        "en": "Quantitative Strategy Analysis WebApp",
    }
    for language, title in expected_titles.items():
        source = get_report_path(language).read_text(encoding="utf-8")
        embedded = extract_embeddable_report(source)

        assert title in embedded
        assert embedded.count("<section") == 10
        assert "TABLE OF CONTENTS" in embedded
        assert "SEARCH MODULE" not in embedded
        assert "<script" not in embedded
        assert '<div class="grid">' not in embedded
        assert '<div class="card">' not in embedded
        assert embedded.count('class="report-scroll-section"') > 20


def test_report_editions_include_composite_analysis_and_frozen_cn_a_comparison() -> None:
    for language in ("zh", "en"):
        source = get_report_path(language).read_text(encoding="utf-8")
        embedded = extract_embeddable_report(source)

        assert 'id="model-composite"' in embedded
        assert 'id="analysis-composite"' in embedded
        assert 'id="baseline-composite"' in embedded
        assert "0.5972" in embedded
        assert "0.5277" in embedded
        assert "0.4984" in embedded
        assert "46/60" in embedded
        assert "research-only" in embedded

        reader = build_report_reader(embedded, modified_ns=42)
        composite_sections = {
            match["id"] for match in filter_report_sections(reader["sections"], "Composite")
        }
        assert {
            "section-2-models",
            "section-3-analysis",
            "section-4-baseline-comparison",
            "section-7-interpretation",
        }.issubset(composite_sections)

    zh_source = get_report_path("zh").read_text(encoding="utf-8")
    en_source = get_report_path("en").read_text(encoding="utf-8")
    assert "fail-closed / unavailable" in zh_source
    assert "SM 与 FSM 各有 20 行" in zh_source
    assert "fails closed as unavailable" in en_source
    assert "SM and FSM each" in en_source and "have 20 rows" in en_source
    assert "冻结 Phase 4/6 数值运行只选择 10 个技术因子" in zh_source
    assert "23 因子 panel 不等于冻结模型的实际输入" in zh_source
    assert "frozen Phase 4/6 numeric run selected only the ten technical factors" in en_source
    assert "23-factor panel is therefore not the" in en_source
    assert "frozen model's actual feature set" in en_source
    assert "不单独验证换手、成本敏感性或 fallback 行为" in zh_source
    assert "does not independently validate turnover, cost sensitivity or fallback behaviour" in en_source
    assert "US 数值状态在本报告中标记为 <strong>unavailable</strong>" in zh_source
    assert "US numeric status is therefore <strong>unavailable</strong>" in en_source
    assert "also beat SM/FSM" not in en_source
    assert "10 技术因子 + 13 市场原生因子的独立综合模型" not in zh_source
    assert "combines those ten technical factors with thirteen" not in en_source


def test_report_editions_keep_bilingual_anchor_contract_in_sync() -> None:
    zh_source = get_report_path("zh").read_text(encoding="utf-8")
    en_source = get_report_path("en").read_text(encoding="utf-8")
    zh_ids = re.findall(r'\bid="([^"]+)"', zh_source)
    en_ids = re.findall(r'\bid="([^"]+)"', en_source)

    assert len(zh_ids) == len(set(zh_ids))
    assert len(en_ids) == len(set(en_ids))
    assert set(zh_ids) == set(en_ids)
    assert "interp-cn-a-composite" in zh_ids
    assert re.search(
        r"<th>方面</th>\s*<th>SM</th>\s*<th>有限状态机</th>\s*"
        r"<th>ML过滤器</th>\s*<th>自适应路由器</th>\s*<th>Composite</th>",
        zh_source,
    )
    assert re.search(
        r"<th>Dimension</th>\s*<th>SM</th>\s*<th>FSM</th>\s*"
        r"<th>ML Filter</th>\s*<th>Adaptive Router</th>\s*<th>Composite</th>",
        en_source,
    )


def test_report_intro_and_keyword_filter_preserve_original_section_markup() -> None:
    source = get_report_path("en").read_text(encoding="utf-8")
    embedded = extract_embeddable_report(source)
    intro, reading = split_report_intro(embedded)
    matches, count = filter_report_sections(reading, "Baseline")

    assert "Quantitative Strategy Analysis WebApp" in intro
    assert "Table of Contents" in reading
    assert count > 0
    assert "Baseline" in matches
    assert matches.count("<section") == count


def test_report_reader_keeps_chapters_and_non_toc_sections_reachable() -> None:
    source = get_report_path("en").read_text(encoding="utf-8")
    reader = build_report_reader(extract_embeddable_report(source), modified_ns=42)

    assert reader["mtime_ns"] == 42
    assert len(reader["sections"]) == 10
    assert reader["sections"][0]["id"] == "run-instructions"
    assert reader["sections"][-1]["id"] == "submission-packaging"
    assert [section["id"] for section in reader["chapters"]][:2] == [
        "section-1-problem-definition",
        "section-2-models",
    ]
    assert len(reader["chapters"]) == 8
    assert any("<table" in section["html"] for section in reader["sections"])
    assert "Submission Packaging" in reader["sections"][-1]["html"]


def test_structured_search_returns_metadata_not_section_markup() -> None:
    source = get_report_path("en").read_text(encoding="utf-8")
    reader = build_report_reader(extract_embeddable_report(source), modified_ns=42)

    matches = filter_report_sections(reader["sections"], "baseline")

    assert matches
    assert all(set(match) == {"id", "title", "snippet"} for match in matches)
    assert all("<section" not in match["snippet"] for match in matches)
    assert any("Baseline" in match["snippet"] for match in matches)
    assert [match["id"] for match in matches] == [
        section["id"]
        for section in reader["sections"]
        if "baseline" in section["search_text"]
    ]


def test_report_navigation_uses_archived_toc_links() -> None:
    source = get_report_path("en").read_text(encoding="utf-8")
    embedded = extract_embeddable_report(source)
    _, reading = split_report_intro(embedded)
    navigation = build_report_navigation(reading, "en")

    assert 'class="report-scroll-rail"' in navigation
    assert "On this page" in navigation
    assert navigation.count('class="report-scroll-rail-chapter"') == 8
    assert navigation.count('class="report-scroll-rail-sub-link"') > 20
    assert navigation.count("data-report-section=") > 28
    assert 'href="#section-7-interpretation"' in navigation
    assert 'href="#interp-fsm-sm"' in navigation
    assert 'data-report-group="6"' in navigation
    assert 'data-report-anchor="interp-fsm-sm"' in embedded


def test_rendered_toc_subitems_do_not_add_browser_ordered_list_numbers() -> None:
    for language in ("zh", "en"):
        source = get_report_path(language).read_text(encoding="utf-8")
        reader = build_report_reader(extract_embeddable_report(source), modified_ns=42)

        toc = final_report.render_report_toc(
            reader,
            language,
            active_section="section-5-parameter-learning",
        )

        assert '<ol class="sub-toc">' not in toc
        assert "<ol" not in toc
        assert '<ul class="sub-toc" role="list">' in toc
        assert "5.1" in toc


def test_rendered_toc_exposes_bilingual_single_open_popover_contract() -> None:
    rendered_by_language: dict[str, str] = {}
    for language in ("zh", "en"):
        source = get_report_path(language).read_text(encoding="utf-8")
        reader = build_report_reader(extract_embeddable_report(source), modified_ns=42)
        rendered_by_language[language] = final_report.render_report_toc(
            reader,
            language,
            active_section="section-2-models",
        )

    for toc in rendered_by_language.values():
        assert toc.count('class="report-toc-popover"') == 8
        assert toc.count('class="report-toc-popover-trigger"') == 8
        assert toc.count('class="report-toc-popover-panel"') == 8
        assert toc.count('aria-expanded="false"') == 8
        assert toc.count('aria-controls="report-toc-panel-') == 8
        assert toc.count('popover="auto"') == 8
        assert toc.count('role="dialog"') == 8
        assert 'role="menu"' not in toc
        assert 'data-report-toc-root="true"' in toc
        assert 'data-report-toc-exclusive="native-auto"' in toc

        panel_ids = re.findall(r'id="(report-toc-panel-[^"]+)"', toc)
        controlled_ids = re.findall(r'aria-controls="(report-toc-panel-[^"]+)"', toc)
        assert len(panel_ids) == len(set(panel_ids)) == 8
        assert controlled_ids == panel_ids

    assert "问题定义和最终答案" in rendered_by_language["zh"]
    assert "Problem Definition &amp; Final Answer" in rendered_by_language["en"]


def test_rendered_toc_preserves_all_links_when_archived_markup_shape_changes() -> None:
    source = get_report_path("en").read_text(encoding="utf-8")
    reader = build_report_reader(extract_embeddable_report(source), modified_ns=42)
    reader["toc_html"] = reader["toc_html"].replace(
        '<summary><a href="#section-2-models">',
        '<summary><a class="chapter-link" href="#section-2-models">',
        1,
    )

    toc = final_report.render_report_toc(
        reader,
        "en",
        active_section="section-2-models",
    )

    assert 'class="report-toc-popover"' not in toc
    assert 'href="#model-rsm"' in toc
    assert "lang=en&amp;section=section-5-parameter-learning#param-space" in toc
    assert toc.count("<details") == 8


def test_rendered_toc_interaction_closes_siblings_and_restores_anchor_scroll() -> None:
    source = get_report_path("en").read_text(encoding="utf-8")
    reader = build_report_reader(extract_embeddable_report(source), modified_ns=42)

    toc = final_report.render_report_toc(
        reader,
        "en",
        active_section="section-2-models",
    )
    script = final_report.build_report_interaction_script()

    assert 'popover="auto"' in toc
    assert 'popovertarget="report-toc-panel-' in toc
    assert 'data-report-toc-script="true"' in script
    assert "aria-expanded" in toc
    assert "report-toc-popover-trigger" in toc
    assert "report-toc-popover-panel" in toc
    assert "beforetoggle" in script
    assert "hidePopover" in script
    assert "Escape" in script
    assert "pointerdown" in script
    assert "hashchange" in script
    assert "scrollIntoView" in script
    assert "document.addEventListener" in script
    assert "supportsPopover" in script
    assert "data-report-fallback-open" in script
    assert "if (!root) return" not in script
    assert "restoreFocus" in script
    assert "focusTarget.focus" in script
    assert "anchorTimers" in script
    assert "cancelAnchorSettling" in script
    assert "2600" in script
    assert "clearTimeout" in script


def test_report_popover_navigation_uses_one_grid_layer() -> None:
    report_css = theme.get_style_bundle_css("report")

    assert (
        ".native-report-shell .report-toc-popover-nav,\n"
        ".native-report-shell .report-toc-popover-nav .sub-toc"
    ) not in report_css
    assert ".native-report-shell .report-toc-popover-nav .sub-toc {" in report_css
    assert "grid-template-columns: repeat(2, minmax(0, 1fr));" in report_css


def test_bilingual_toc_uses_local_hashes_and_cross_section_routes() -> None:
    active_section = "section-2-models"
    for language in ("zh", "en"):
        source = get_report_path(language).read_text(encoding="utf-8")
        reader = build_report_reader(extract_embeddable_report(source), modified_ns=42)
        toc = final_report.render_report_toc(
            reader,
            language,
            active_section=active_section,
        )
        hrefs = [unescape(value) for value in re.findall(r'href="([^"]+)"', toc)]

        assert hrefs
        for href in hrefs:
            parsed = urlsplit(href)
            fragment = parsed.fragment
            assert fragment in reader["anchor_to_section"]
            owner_section = reader["anchor_to_section"][fragment]
            if owner_section == active_section:
                assert href == f"#{fragment}"
            else:
                assert parse_qs(parsed.query)["lang"] == [language]
                assert parse_qs(parsed.query)["section"] == [owner_section]

        assert "#model-rsm" in hrefs
        assert any("section=section-5-parameter-learning#param-space" in href for href in hrefs)


def test_render_html_keeps_javascript_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, dict[str, bool]]] = []

    class _FakeHtmlStreamlit:
        @staticmethod
        def html(body: str, **kwargs: bool) -> None:
            calls.append((body, kwargs))

    monkeypatch.setattr(theme, "st", _FakeHtmlStreamlit())

    theme.render_html("<div>safe</div>", localize=False)
    theme.render_html(
        '<script data-report-toc-script="true"></script>',
        localize=False,
        unsafe_allow_javascript=True,
    )

    assert calls == [
        ("<div>safe</div>", {"unsafe_allow_javascript": False}),
        (
            '<script data-report-toc-script="true"></script>',
            {"unsafe_allow_javascript": True},
        ),
    ]


class _FakeBlock:
    def __init__(self, host: "_FakeReportStreamlit") -> None:
        self._host = host

    def __enter__(self) -> "_FakeReportStreamlit":
        return self._host

    def __exit__(self, exc_type, exc, traceback) -> bool:
        return False


class _FakeReportStreamlit:
    def __init__(
        self,
        *,
        section: str = "",
        draft: str = "",
        submit: bool = False,
        clear: bool = False,
    ) -> None:
        self.session_state: dict[str, str] = {}
        self.query_params = {"section": section} if section else {}
        self.draft = draft
        self.submit = submit
        self.clear = clear
        self.form_submit_calls = 0
        self.column_specs: list[tuple[tuple[float, ...], str]] = []
        self.captions: list[str] = []
        self.infos: list[str] = []

    def form(self, key: str, *, clear_on_submit: bool):
        assert key == "final-report-search"
        assert clear_on_submit is False
        return _FakeBlock(self)

    def container(self, *, key: str):
        assert key == "final-report-search-shell"
        return _FakeBlock(self)

    def text_input(self, label: str, *, placeholder: str, key: str) -> str:
        _ = label, placeholder
        self.session_state[key] = self.draft
        return self.draft

    def columns(self, spec: tuple[float, ...], *, gap: str):
        self.column_specs.append((spec, gap))
        return tuple(_FakeBlock(self) for _ in spec)

    def form_submit_button(self, label: str, *, on_click=None) -> bool:
        _ = label
        self.form_submit_calls += 1
        clicked = (self.submit and self.form_submit_calls == 1) or (self.clear and self.form_submit_calls == 2)
        if clicked and on_click is not None:
            on_click()
        return clicked

    def caption(self, message: str) -> None:
        self.captions.append(message)

    def info(self, message: str) -> None:
        self.infos.append(message)


def test_query_section_selects_requested_non_chapter_section(monkeypatch) -> None:
    source = get_report_path("en").read_text(encoding="utf-8")
    reader = build_report_reader(extract_embeddable_report(source), modified_ns=42)
    fake_st = _FakeReportStreamlit(section="submission-packaging")
    monkeypatch.setattr(final_report, "st", fake_st)

    active = final_report._get_active_section(reader)

    assert active["id"] == "submission-packaging"
    assert fake_st.session_state["final_report_active_section"] == "submission-packaging"


def test_invalid_query_section_falls_back_to_first_chapter(monkeypatch) -> None:
    source = get_report_path("en").read_text(encoding="utf-8")
    reader = build_report_reader(extract_embeddable_report(source), modified_ns=42)
    fake_st = _FakeReportStreamlit(section="not-a-real-section")
    monkeypatch.setattr(final_report, "st", fake_st)

    active = final_report._get_active_section(reader)

    assert active["id"] == "section-1-problem-definition"


def test_invalid_query_section_ignores_a_saved_chapter(monkeypatch) -> None:
    source = get_report_path("en").read_text(encoding="utf-8")
    reader = build_report_reader(extract_embeddable_report(source), modified_ns=42)
    fake_st = _FakeReportStreamlit(section="not-a-real-section")
    fake_st.session_state[final_report.ACTIVE_SECTION_STATE_KEY] = "section-5-parameter-learning"
    monkeypatch.setattr(final_report, "st", fake_st)

    active = final_report._get_active_section(reader)

    assert active["id"] == "section-1-problem-definition"


def test_same_section_search_result_clears_search_and_opens_the_chapter(monkeypatch) -> None:
    source = get_report_path("en").read_text(encoding="utf-8")
    reader = build_report_reader(extract_embeddable_report(source), modified_ns=42)
    fake_st = _FakeReportStreamlit(section="section-2-models")
    fake_st.query_params[final_report.REPORT_RESULT_QUERY_KEY] = "open"
    fake_st.session_state[final_report.ACTIVE_SECTION_STATE_KEY] = "section-2-models"
    fake_st.session_state[final_report.SUBMITTED_QUERY_STATE_KEY] = "baseline"
    monkeypatch.setattr(final_report, "st", fake_st)

    active = final_report._get_active_section(reader)

    assert active["id"] == "section-2-models"
    assert fake_st.session_state[final_report.SUBMITTED_QUERY_STATE_KEY] == ""
    assert final_report.REPORT_RESULT_QUERY_KEY not in fake_st.query_params


def test_search_only_filters_after_form_submission(monkeypatch) -> None:
    source = get_report_path("en").read_text(encoding="utf-8")
    reader = build_report_reader(extract_embeddable_report(source), modified_ns=42)
    fake_st = _FakeReportStreamlit(draft="baseline", submit=False)
    rendered: list[str] = []
    monkeypatch.setattr(final_report, "st", fake_st)
    monkeypatch.setattr(final_report, "render_html", lambda markup, **kwargs: rendered.append(markup))

    matches = final_report._render_search(reader, "en")

    assert matches is None
    assert rendered == []
    assert "final_report_submitted_query" not in fake_st.session_state
    assert fake_st.column_specs == [((1, 1.35, 5), "small")]


def test_search_submission_renders_only_metadata_results(monkeypatch) -> None:
    source = get_report_path("en").read_text(encoding="utf-8")
    reader = build_report_reader(extract_embeddable_report(source), modified_ns=42)
    fake_st = _FakeReportStreamlit(draft="baseline", submit=True)
    rendered: list[str] = []
    monkeypatch.setattr(final_report, "st", fake_st)
    monkeypatch.setattr(final_report, "render_html", lambda markup, **kwargs: rendered.append(markup))

    matches = final_report._render_search(reader, "en")

    assert matches
    assert fake_st.session_state["final_report_submitted_query"] == "baseline"
    assert fake_st.captions
    assert len(rendered) == 1
    assert "report-search-result" in rendered[0]
    assert "report_result=open" in rendered[0]
    assert "<section" not in rendered[0]


def test_clear_search_uses_callback_safe_state_reset(monkeypatch) -> None:
    source = get_report_path("en").read_text(encoding="utf-8")
    reader = build_report_reader(extract_embeddable_report(source), modified_ns=42)
    fake_st = _FakeReportStreamlit(draft="baseline", clear=True)
    fake_st.session_state["final_report_submitted_query"] = "baseline"
    monkeypatch.setattr(final_report, "st", fake_st)

    matches = final_report._render_search(reader, "en")

    assert matches is None
    assert fake_st.session_state["final_report_search_draft"] == ""
    assert fake_st.session_state["final_report_submitted_query"] == ""


def test_report_toc_links_preserve_language_and_load_owning_section() -> None:
    source = get_report_path("en").read_text(encoding="utf-8")
    reader = build_report_reader(extract_embeddable_report(source), modified_ns=42)

    toc = final_report.render_report_toc(
        reader,
        "zh",
        active_section="section-2-models",
    )
    navigation = build_report_navigation(
        reader["toc_html"],
        "en",
        active_section="section-2-models",
        anchor_to_section=reader["anchor_to_section"],
    )

    assert "lang=zh&amp;section=section-1-problem-definition#sec-1-1" in toc
    assert 'href="#model-sm"' in navigation
    assert "lang=en&amp;section=section-5-parameter-learning#param-space" in navigation
    assert "report-scroll-rail-chapter is-active" in navigation


def test_cached_report_reader_invalidates_when_mtime_changes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "report.html"
    report_path.write_text("placeholder", encoding="utf-8")
    calls: list[str] = []
    final_report.load_embeddable_report.clear()
    monkeypatch.setattr(final_report, "extract_embeddable_report", lambda source: source)
    monkeypatch.setattr(
        final_report,
        "build_report_reader",
        lambda source, modified_ns: calls.append(source)
        or {"source": source, "mtime_ns": modified_ns},
    )

    first = final_report.load_embeddable_report(str(report_path), 1)
    second = final_report.load_embeddable_report(str(report_path), 1)
    refreshed = final_report.load_embeddable_report(str(report_path), 2)

    assert first == second == {"source": "placeholder", "mtime_ns": 1}
    assert refreshed == {"source": "placeholder", "mtime_ns": 2}
    assert calls == ["placeholder", "placeholder"]
    final_report.load_embeddable_report.clear()


def test_report_route_has_no_iframe_component() -> None:
    app_source = (REPO_ROOT / "app.py").read_text(encoding="utf-8")
    page_source = (REPO_ROOT / "ui" / "final_report.py").read_text(encoding="utf-8")
    theme_source = (REPO_ROOT / "ui" / "theme.py").read_text(encoding="utf-8")

    assert "_render_final_report_route" in app_source
    assert "components.html" not in app_source
    assert "components.html" not in page_source
    assert "render_html(" in page_source
    assert 'class="report-reading-document"' in page_source
    assert 't("帮助", "Help")' in theme_source
    assert ".block-container:has(.native-report-intro)" in theme_source
    assert "@media (min-width: 1600px)" in theme_source
    assert "position: fixed;" in theme_source
