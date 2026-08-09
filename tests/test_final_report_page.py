from pathlib import Path

import pytest
import ui.final_report as final_report
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

    toc = final_report.render_report_toc(reader, "zh")
    navigation = build_report_navigation(
        reader["toc_html"],
        "en",
        active_section="section-2-models",
        anchor_to_section=reader["anchor_to_section"],
    )

    assert "lang=zh&amp;section=section-1-problem-definition#sec-1-1" in toc
    assert "lang=en&amp;section=section-2-models#model-sm" in navigation
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
