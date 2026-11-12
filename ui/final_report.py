"""Render archived course reports as native, chapter-sized Strategy Lab content."""

from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import streamlit as st

from core.perf import performance_span
from ui.theme import get_ui_language, render_html, render_route_nav, route_href, t


REPORTS_ROOT = Path(__file__).resolve().parents[1] / "reports"
REPORT_FILENAMES = {"zh": "Final_Report_zh.html", "en": "Final_Report.html"}
MAIN_OPEN_MARKER = '<main class="shell">'
MAIN_CLOSE_MARKER = "</main>"
SEARCH_MARKER = "<!-- SEARCH MODULE"
TOC_MARKER = "<!-- TABLE OF CONTENTS"
SECTION_PATTERN = re.compile(r"<section\b[^>]*>.*?</section>", re.IGNORECASE | re.DOTALL)
SECTION_ID_PATTERN = re.compile(r'<section\b[^>]*\bid="([A-Za-z][A-Za-z0-9_-]*)"[^>]*>', re.IGNORECASE)
SECTION_TITLE_PATTERN = re.compile(r"<h2\b[^>]*>(.*?)</h2>", re.IGNORECASE | re.DOTALL)
TAG_PATTERN = re.compile(r"<[^>]+>")
TOC_GROUP_PATTERN = re.compile(
    r'<details\b[^>]*>\s*<summary>\s*<a href="#([^"]+)">(.*?)</a>\s*</summary>'
    r'\s*<ol class="sub-toc">(.*?)</ol>\s*</details>',
    re.IGNORECASE | re.DOTALL,
)
SUB_TOC_LINK_PATTERN = re.compile(
    r'<li>\s*<a href="#([^"]+)">(.*?)</a>\s*</li>',
    re.IGNORECASE | re.DOTALL,
)
TOC_ANCHOR_HREF_PATTERN = re.compile(
    r'(?P<prefix>\bhref\s*=\s*)(?P<quote>["\'])#'
    r'(?P<anchor>[A-Za-z][A-Za-z0-9_-]*)(?P=quote)',
    re.IGNORECASE,
)
SAFE_ANCHOR_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
ID_TAG_PATTERN = re.compile(
    r'<[A-Za-z][^>]*\bid="([A-Za-z][A-Za-z0-9_-]*)"[^>]*>',
    re.IGNORECASE,
)
HERO_METADATA_PATTERN = re.compile(
    r"\s*<div class=\"grid\">\s*(?:<div class=\"card\">.*?</div>\s*){3}</div>",
    re.IGNORECASE | re.DOTALL,
)
ACTIVE_SECTION_STATE_KEY = "final_report_active_section"
SUBMITTED_QUERY_STATE_KEY = "final_report_submitted_query"
SEARCH_DRAFT_STATE_KEY = "final_report_search_draft"
REPORT_RESULT_QUERY_KEY = "report_result"


def _visible_text(markup: str) -> str:
    return " ".join(html.unescape(TAG_PATTERN.sub(" ", markup)).split())


def wrap_report_subsections(report_body: str) -> str:
    """Wrap TOC-linked subsections so CSS scroll timelines span their full content."""
    subsection_ids = {
        subsection_id
        for sub_toc_markup in TOC_GROUP_PATTERN.findall(report_body)
        for subsection_id, _ in SUB_TOC_LINK_PATTERN.findall(sub_toc_markup[2])
        if SAFE_ANCHOR_PATTERN.fullmatch(subsection_id)
    }
    if not subsection_ids:
        return report_body

    def wrap_section(match: re.Match[str]) -> str:
        section_markup = match.group(0)
        closing_start = section_markup.lower().rfind("</section>")
        anchors = [
            anchor_match
            for anchor_match in ID_TAG_PATTERN.finditer(section_markup, 0, closing_start)
            if anchor_match.group(1) in subsection_ids
        ]
        if closing_start < 0 or not anchors:
            return section_markup

        parts = [section_markup[: anchors[0].start()]]
        for index, anchor_match in enumerate(anchors):
            segment_end = anchors[index + 1].start() if index + 1 < len(anchors) else closing_start
            anchor_id = anchor_match.group(1)
            parts.append(
                f'<div class="report-scroll-section" data-report-anchor="{anchor_id}">'
                f"{section_markup[anchor_match.start() : segment_end]}</div>"
            )
        parts.append(section_markup[closing_start:])
        return "".join(parts)

    return SECTION_PATTERN.sub(wrap_section, report_body)


def get_report_path(language: str) -> Path:
    """Return the archived report matching the normalized site language."""
    normalized = "zh" if str(language).lower().startswith("zh") else "en"
    return REPORTS_ROOT / REPORT_FILENAMES[normalized]


def extract_embeddable_report(source_html: str) -> str:
    """Extract report content while removing its standalone document shell and script UI."""
    main_start = source_html.find(MAIN_OPEN_MARKER)
    main_end = source_html.rfind(MAIN_CLOSE_MARKER)
    if main_start < 0 or main_end <= main_start:
        raise ValueError("Report document does not contain the expected main shell")

    body = source_html[main_start + len(MAIN_OPEN_MARKER) : main_end]
    search_start = body.find(SEARCH_MARKER)
    toc_start = body.find(TOC_MARKER)
    if search_start >= 0 and toc_start > search_start:
        body = body[:search_start] + body[toc_start:]
    body = HERO_METADATA_PATTERN.sub("", body, count=1)
    return wrap_report_subsections(body).strip()


def split_report_intro(report_body: str) -> tuple[str, str]:
    """Split the original hero from the TOC/body so the native search can sit between them."""
    toc_start = report_body.find(TOC_MARKER)
    if toc_start < 0:
        return "", report_body
    return report_body[:toc_start].strip(), report_body[toc_start:].strip()


def _section_id(section_markup: str) -> str | None:
    match = SECTION_ID_PATTERN.search(section_markup)
    return match.group(1) if match and SAFE_ANCHOR_PATTERN.fullmatch(match.group(1)) else None


def _section_title(section_markup: str, section_id: str) -> str:
    match = SECTION_TITLE_PATTERN.search(section_markup)
    return _visible_text(match.group(1)) if match else section_id.replace("-", " ").title()


def build_report_reader(report_body: str, modified_ns: int) -> dict[str, Any]:
    """Build a serializable indexed view while keeping original section markup intact."""
    intro_html, reading_body = split_report_intro(report_body)
    section_matches = tuple(SECTION_PATTERN.findall(reading_body))
    sections = tuple(
        {
            "id": section_id,
            "title": _section_title(section_markup, section_id),
            "html": section_markup,
            "visible_text": _visible_text(section_markup),
            "search_text": _visible_text(section_markup).casefold(),
        }
        for section_markup in section_matches
        if (section_id := _section_id(section_markup)) is not None
    )
    chapters = tuple(section for section in sections if section["id"].startswith("section-"))
    first_section_start = reading_body.find(section_matches[0]) if section_matches else len(reading_body)
    toc_html = reading_body[:first_section_start].strip()
    anchor_to_section: dict[str, str] = {}
    for section in sections:
        for anchor_id in ID_TAG_PATTERN.findall(section["html"]):
            if SAFE_ANCHOR_PATTERN.fullmatch(anchor_id):
                anchor_to_section[anchor_id] = section["id"]

    return {
        "intro_html": intro_html,
        "toc_html": toc_html,
        "sections": sections,
        "chapters": chapters,
        "anchor_to_section": anchor_to_section,
        "mtime_ns": modified_ns,
    }


def filter_report_sections(
    report_body_or_sections: str | tuple[dict[str, str], ...], query: str
) -> tuple[str, int] | tuple[dict[str, str], ...]:
    """Filter legacy report HTML or structured sections with the same visible-text semantics."""
    normalized_query = str(query or "").strip().casefold()
    if isinstance(report_body_or_sections, str):
        if not normalized_query:
            return report_body_or_sections, 0
        matched_sections = [
            section_markup
            for section_markup in SECTION_PATTERN.findall(report_body_or_sections)
            if normalized_query in _visible_text(section_markup).casefold()
        ]
        return "\n".join(matched_sections), len(matched_sections)

    if not normalized_query:
        return tuple()
    return tuple(
        {
            "id": section["id"],
            "title": section["title"],
            "snippet": _search_snippet(
                section["visible_text"], section["search_text"], normalized_query
            ),
        }
        for section in report_body_or_sections
        if normalized_query in section["search_text"]
    )


def _search_snippet(
    visible_text: str,
    normalized_text: str,
    query: str,
    limit: int = 220,
) -> str:
    index = normalized_text.find(query)
    if index < 0:
        return visible_text[:limit]
    start = max(0, index - 72)
    end = min(len(visible_text), index + len(query) + 140)
    prefix = "..." if start else ""
    suffix = "..." if end < len(visible_text) else ""
    return f"{prefix}{visible_text[start:end]}{suffix}"


def _report_section_href(
    section_id: str,
    language: str,
    anchor_id: str | None = None,
    *,
    clear_search: bool = False,
) -> str:
    path = route_href("final-report", language=language)
    separator = "&" if "?" in path else "?"
    fragment = f"#{anchor_id}" if anchor_id else ""
    query = {"section": section_id}
    if clear_search:
        query[REPORT_RESULT_QUERY_KEY] = "open"
    return f"{path}{separator}{urlencode(query)}{fragment}"


def _report_anchor_href(
    anchor_id: str,
    owner_section: str,
    language: str,
    active_section: str | None,
) -> str:
    """Keep same-chapter jumps local while routing unloaded anchors through their chapter."""
    if active_section and owner_section == active_section:
        return f"#{anchor_id}"
    return _report_section_href(owner_section, language, anchor_id)


def _rewrite_report_toc_links(
    toc_html: str,
    anchor_to_section: dict[str, str],
    language: str,
    active_section: str | None,
) -> str:
    """Keep the archived TOC usable if its structure no longer matches the popover parser."""

    def replace_href(match: re.Match[str]) -> str:
        anchor_id = match.group("anchor")
        owner_section = anchor_to_section.get(anchor_id)
        if not owner_section:
            return match.group(0)
        href = _report_anchor_href(anchor_id, owner_section, language, active_section)
        quote = match.group("quote")
        return f'{match.group("prefix")}{quote}{html.escape(href, quote=True)}{quote}'

    return TOC_ANCHOR_HREF_PATTERN.sub(replace_href, toc_html)


def render_report_toc(
    reader: dict[str, Any],
    language: str,
    active_section: str | None = None,
) -> str:
    """Rebuild the archived TOC as mutually exclusive native popovers."""
    anchor_to_section = reader["anchor_to_section"]
    groups = TOC_GROUP_PATTERN.findall(reader["toc_html"])
    source_anchor_ids = [
        match.group("anchor")
        for match in TOC_ANCHOR_HREF_PATTERN.finditer(reader["toc_html"])
    ]
    parsed_anchor_ids: list[str] = []
    for section_id, _label_markup, sub_toc_markup in groups:
        parsed_anchor_ids.append(section_id)
        parsed_anchor_ids.extend(
            anchor_id
            for anchor_id, _subsection_markup in SUB_TOC_LINK_PATTERN.findall(sub_toc_markup)
        )
    if not groups or parsed_anchor_ids != source_anchor_ids:
        return _rewrite_report_toc_links(
            reader["toc_html"],
            anchor_to_section,
            language,
            active_section,
        )

    toc_label = "目录" if language == "zh" else "Contents"
    close_label = "关闭子目录" if language == "zh" else "Close subsection list"
    rows: list[str] = []
    for group_index, (section_id, label_markup, sub_toc_markup) in enumerate(groups):
        if not SAFE_ANCHOR_PATTERN.fullmatch(section_id):
            continue
        owner_section = anchor_to_section.get(section_id, section_id)
        chapter_href = _report_anchor_href(
            section_id,
            owner_section,
            language,
            active_section,
        )
        chapter_label = _visible_text(label_markup)
        panel_id = f"report-toc-panel-{section_id}"
        panel_title_id = f"report-toc-title-{section_id}"
        anchor_name = f"--report-toc-anchor-{group_index}"
        expand_label = (
            f"展开“{chapter_label}”子目录"
            if language == "zh"
            else f"Open subsections for {chapter_label}"
        )
        sub_links: list[str] = []
        for anchor_id, subsection_markup in SUB_TOC_LINK_PATTERN.findall(sub_toc_markup):
            if not SAFE_ANCHOR_PATTERN.fullmatch(anchor_id):
                continue
            subsection_owner = anchor_to_section.get(anchor_id)
            if not subsection_owner:
                continue
            subsection_href = _report_anchor_href(
                anchor_id,
                subsection_owner,
                language,
                active_section,
            )
            subsection_label = _visible_text(subsection_markup)
            sub_links.append(
                f'<li><a href="{html.escape(subsection_href, quote=True)}" '
                f'data-report-anchor="{html.escape(anchor_id, quote=True)}">'
                f"{html.escape(subsection_label)}</a></li>"
            )

        rows.append(
            f'<li class="report-toc-popover" data-report-toc-align="'
            f'{"end" if group_index % 2 else "start"}" style="anchor-name: {anchor_name};">'
            f'<div class="report-toc-row">'
            f'<button class="report-toc-popover-trigger" type="button" '
            f'popovertarget="{panel_id}" aria-controls="{panel_id}" aria-expanded="false" '
            f'aria-label="{html.escape(expand_label, quote=True)}"><span aria-hidden="true">+</span></button>'
            f'<a class="report-toc-chapter-link" href="{html.escape(chapter_href, quote=True)}" '
            f'data-report-anchor="{html.escape(section_id, quote=True)}">{html.escape(chapter_label)}</a>'
            f"</div>"
            f'<div id="{panel_id}" class="report-toc-popover-panel" popover="auto" role="dialog" '
            f'aria-labelledby="{panel_title_id}" style="position-anchor: {anchor_name};">'
            f'<div class="report-toc-popover-heading"><strong id="{panel_title_id}">'
            f"{html.escape(chapter_label)}</strong>"
            f'<button class="report-toc-popover-close" type="button" popovertarget="{panel_id}" '
            f'popovertargetaction="hide" aria-label="{html.escape(close_label, quote=True)}">×</button></div>'
            f'<nav class="report-toc-popover-nav" aria-label="{html.escape(expand_label, quote=True)}">'
            f'<ul class="sub-toc" role="list">{"".join(sub_links)}</ul></nav></div></li>'
        )

    return (
        f'<nav class="toc report-toc" id="toc-nav" aria-label="{toc_label}" '
        f'data-report-toc-root="true" data-report-toc-exclusive="native-auto">'
        f"<h2>{toc_label}</h2><ul class=\"report-toc-list\" role=\"list\">{''.join(rows)}</ul></nav>"
    )


def build_report_interaction_script() -> str:
    """Return the trusted report-only bridge for popover state and post-rerun anchors."""
    return """
<script data-report-toc-script="true">
(() => {
  const controllerKey = "__strategyReportTocController";
  const previousController = window[controllerKey];
  if (previousController && typeof previousController.abort === "function") {
    previousController.abort();
  }
  const controller = new AbortController();
  window[controllerKey] = controller;
  const signal = controller.signal;
  const anchorTimers = new Set();
  signal.addEventListener("abort", () => {
    anchorTimers.forEach((timerId) => window.clearTimeout(timerId));
    anchorTimers.clear();
  }, {once: true});
  const scheduleAnchorTask = (callback, delay) => {
    const timerId = window.setTimeout(() => {
      anchorTimers.delete(timerId);
      if (!signal.aborted) callback();
    }, delay);
    anchorTimers.add(timerId);
  };
  const supportsPopover = typeof HTMLElement !== "undefined"
    && typeof HTMLElement.prototype.showPopover === "function";
  const readings = Array.from(document.querySelectorAll(".native-report-reading"));
  const reading = readings[readings.length - 1];
  if (!reading) return;
  const root = reading.querySelector('[data-report-toc-root="true"]');
  const panels = root
    ? Array.from(root.querySelectorAll(".report-toc-popover-panel"))
    : [];
  const triggers = root
    ? Array.from(root.querySelectorAll(".report-toc-popover-trigger"))
    : [];
  const triggerFor = (panel) => triggers.find(
    (trigger) => trigger.getAttribute("aria-controls") === panel.id
  );
  const syncPanel = (panel, expanded) => {
    const trigger = triggerFor(panel);
    if (!trigger) return;
    trigger.setAttribute("aria-expanded", expanded ? "true" : "false");
    const icon = trigger.querySelector('[aria-hidden="true"]');
    if (icon) icon.textContent = expanded ? "−" : "+";
  };
  const isOpen = (panel) => {
    if (!supportsPopover) {
      return panel.getAttribute("data-report-fallback-open") === "true";
    }
    try {
      return panel.matches(":popover-open");
    } catch (_error) {
      return false;
    }
  };
  const closePanel = (panel, restoreFocus = false) => {
    if (!isOpen(panel)) return;
    if (supportsPopover && typeof panel.hidePopover === "function") {
      panel.hidePopover();
      return;
    }
    panel.hidden = true;
    panel.setAttribute("aria-hidden", "true");
    panel.removeAttribute("data-report-fallback-open");
    syncPanel(panel, false);
    if (restoreFocus) {
      const trigger = triggerFor(panel);
      if (trigger) trigger.focus();
    }
  };
  const openFallbackPanel = (panel) => {
    panels.forEach((sibling) => {
      if (sibling !== panel) closePanel(sibling);
    });
    panel.hidden = false;
    panel.setAttribute("aria-hidden", "false");
    panel.setAttribute("data-report-fallback-open", "true");
    syncPanel(panel, true);
    const focusTarget = panel.querySelector(".report-toc-popover-close, a[href]");
    if (focusTarget instanceof HTMLElement) {
      focusTarget.focus({preventScroll: true});
    }
  };

  panels.forEach((panel) => {
    if (!supportsPopover) {
      panel.hidden = true;
      panel.setAttribute("aria-hidden", "true");
      const trigger = triggerFor(panel);
      if (trigger) {
        trigger.addEventListener("click", (event) => {
          event.preventDefault();
          if (isOpen(panel)) closePanel(panel);
          else openFallbackPanel(panel);
        }, {signal});
      }
      const closeButton = panel.querySelector(".report-toc-popover-close");
      if (closeButton) {
        closeButton.addEventListener("click", (event) => {
          event.preventDefault();
          closePanel(panel, true);
        }, {signal});
      }
    }
    panel.addEventListener("beforetoggle", (event) => {
      if (event.newState !== "open") return;
      panels.forEach((sibling) => {
        if (sibling !== panel) closePanel(sibling);
      });
    }, {signal});
    panel.addEventListener("toggle", (event) => {
      syncPanel(panel, event.newState === "open");
    }, {signal});
    panel.querySelectorAll("a[href]").forEach((link) => {
      link.addEventListener("click", () => closePanel(panel), {signal});
    });
  });

  document.addEventListener("keydown", (event) => {
    cancelAnchorSettling();
    if (event.key !== "Escape") return;
    panels.forEach((panel) => closePanel(panel, true));
  }, {signal});
  document.addEventListener("pointerdown", (event) => {
    cancelAnchorSettling();
    const openPanel = panels.find(isOpen);
    if (!openPanel) return;
    const trigger = triggerFor(openPanel);
    const target = event.target;
    if (target instanceof Node && (
      openPanel.contains(target) || (trigger && trigger.contains(target))
    )) {
      if (target !== openPanel) return;
      const bounds = openPanel.getBoundingClientRect();
      const insidePanel = event.clientX >= bounds.left && event.clientX <= bounds.right
        && event.clientY >= bounds.top && event.clientY <= bounds.bottom;
      if (insidePanel) return;
    }
    closePanel(openPanel);
  }, {signal, capture: true});

  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const validAnchor = /^[A-Za-z][A-Za-z0-9_-]*$/;
  const decodeAnchor = (value) => {
    try {
      return decodeURIComponent(value);
    } catch (_error) {
      return "";
    }
  };
  const findNewestTarget = (anchorId) => {
    const localTarget = reading ? reading.querySelector(`[id="${anchorId}"]`) : null;
    if (localTarget) return localTarget;
    const targets = document.querySelectorAll(`[id="${anchorId}"]`);
    return targets.length ? targets[targets.length - 1] : null;
  };
  const scrollToAnchor = (anchorId, behavior = reducedMotion ? "auto" : "smooth") => {
    if (!validAnchor.test(anchorId)) return false;
    const target = findNewestTarget(anchorId);
    if (!target) return false;
    target.scrollIntoView({
      behavior,
      block: "start",
    });
    if (!target.hasAttribute("tabindex")) {
      target.setAttribute("tabindex", "-1");
      target.setAttribute("data-report-focus-target", "true");
    }
    target.focus({preventScroll: true});
    return true;
  };
  let anchorRun = 0;
  const cancelAnchorSettling = () => {
    anchorRun += 1;
    anchorTimers.forEach((timerId) => window.clearTimeout(timerId));
    anchorTimers.clear();
  };
  const scrollToCurrentHash = () => {
    cancelAnchorSettling();
    const run = anchorRun;
    const anchorId = decodeAnchor(window.location.hash.slice(1));
    if (!anchorId) return;
    [0, 120, 400, 900, 1600, 2600].forEach((delay, index) => {
      scheduleAnchorTask(() => {
        if (run !== anchorRun) return;
        window.requestAnimationFrame(() => {
          if (signal.aborted || run !== anchorRun) return;
          scrollToAnchor(
            anchorId,
            index === 0 && !reducedMotion ? "smooth" : "auto"
          );
        });
      }, delay);
    });
  };

  document.addEventListener("wheel", cancelAnchorSettling, {signal, passive: true});
  document.addEventListener("touchstart", cancelAnchorSettling, {signal, passive: true});

  window.addEventListener("hashchange", scrollToCurrentHash, {signal});
  document.addEventListener("click", (event) => {
    cancelAnchorSettling();
    if (!(event.target instanceof Element)) return;
    const link = event.target.closest('.native-report-reading a[href^="#"]');
    if (!link) return;
    const anchorId = decodeAnchor(link.getAttribute("href").slice(1));
    scheduleAnchorTask(() => scrollToAnchor(anchorId), 0);
  }, {signal});
  scrollToCurrentHash();
})();
</script>
""".strip()


def build_report_navigation(
    report_body: str,
    language: str,
    active_section: str | None = None,
    anchor_to_section: dict[str, str] | None = None,
) -> str:
    """Build a hierarchical wide-screen rail from the archived report TOC."""
    groups: list[str] = []
    timeline_names: list[str] = []
    timeline_rules: list[str] = []
    link_index = 0

    def build_link(section_id: str, label_markup: str, class_name: str) -> tuple[str, str]:
        nonlocal link_index
        if not SAFE_ANCHOR_PATTERN.fullmatch(section_id):
            return "", ""
        label = _visible_text(label_markup)
        timeline_name = f"--report-rail-{link_index}"
        timeline_names.append(timeline_name)
        target_selector = (
            f'.report-scroll-section[data-report-anchor="{section_id}"]'
            if class_name == "report-scroll-rail-sub-link"
            else f"#{section_id}"
        )
        timeline_rules.extend(
            [
                f".native-report-reading {target_selector} {{ view-timeline: {timeline_name} block; }}",
                f'.report-scroll-rail a[data-report-index="{link_index}"] '
                f"{{ animation-timeline: {timeline_name}; }}",
            ]
        )
        owner_section = (anchor_to_section or {}).get(section_id, section_id)
        href = (
            _report_anchor_href(section_id, owner_section, language, active_section)
            if anchor_to_section is not None
            else f"#{section_id}"
        )
        active_class = " is-active" if owner_section == active_section else ""
        link_markup = (
            f'<a class="{class_name}{active_class}" href="{html.escape(href, quote=True)}" '
            f'data-report-section="{html.escape(section_id, quote=True)}" '
            f'data-report-index="{link_index}" title="{html.escape(label, quote=True)}">'
            f"{html.escape(label)}</a>"
        )
        link_index += 1
        return link_markup, timeline_name

    for group_index, (section_id, label_markup, sub_toc_markup) in enumerate(
        TOC_GROUP_PATTERN.findall(report_body)
    ):
        chapter_link, chapter_timeline = build_link(section_id, label_markup, "report-scroll-rail-chapter")
        sub_link_results = [
            build_link(subsection_id, subsection_label, "report-scroll-rail-sub-link")
            for subsection_id, subsection_label in SUB_TOC_LINK_PATTERN.findall(sub_toc_markup)
        ]
        sub_links = [link for link, _ in sub_link_results if link]
        if chapter_link:
            timeline_rules.append(
                f'.report-scroll-rail-group[data-report-group="{group_index}"] '
                f".report-scroll-rail-sub {{ animation-timeline: {chapter_timeline}; }}"
            )
            groups.append(
                f'<div class="report-scroll-rail-group" data-report-group="{group_index}">'
                f"{chapter_link}<div class=\"report-scroll-rail-sub\">{''.join(sub_links)}</div></div>"
            )

    if not groups:
        return ""

    rail_label = "本页目录" if language == "zh" else "On this page"
    timeline_styles = (
        "<style>"
        f'.native-report-reading {{ timeline-scope: {", ".join(timeline_names)}; }}'
        f"{''.join(timeline_rules)}"
        "</style>"
    )
    return (
        f"{timeline_styles}<aside class=\"report-scroll-rail\" aria-label=\"{html.escape(rail_label, quote=True)}\">"
        f"<span class=\"report-scroll-rail-label\">{rail_label}</span><nav>{''.join(groups)}</nav></aside>"
    )


@st.cache_data(show_spinner=False)
def load_embeddable_report(report_path: str, modified_ns: int) -> dict[str, Any]:
    """Read and index one report edition; mtime keeps the cache coherent."""
    with performance_span("report", "parse", source=Path(report_path).name):
        source_html = Path(report_path).read_text(encoding="utf-8")
        return build_report_reader(extract_embeddable_report(source_html), modified_ns)


def _query_section_id() -> str:
    try:
        value = st.query_params.get("section", "")
        if isinstance(value, (list, tuple)):
            value = value[-1] if value else ""
        return str(value or "")
    except (AttributeError, KeyError, TypeError):
        return ""


def _consume_report_result_request() -> bool:
    """Consume the one-shot query marker used when a search result opens a chapter."""
    try:
        value = st.query_params.get(REPORT_RESULT_QUERY_KEY, "")
        if isinstance(value, (list, tuple)):
            value = value[-1] if value else ""
        requested = str(value or "") == "open"
        if requested:
            del st.query_params[REPORT_RESULT_QUERY_KEY]
        return requested
    except (AttributeError, KeyError, TypeError):
        return False


def _get_active_section(reader: dict[str, Any]) -> dict[str, str]:
    sections = reader["sections"]
    if not sections:
        raise ValueError("Report document does not contain a section")
    available = {section["id"]: section for section in sections}
    default_section = reader["chapters"][0] if reader["chapters"] else sections[0]
    query_section = _query_section_id()
    report_result_requested = _consume_report_result_request()
    saved_section = str(st.session_state.get(ACTIVE_SECTION_STATE_KEY, ""))
    active = (
        available.get(query_section, default_section)
        if query_section
        else available.get(saved_section, default_section)
    )
    if report_result_requested or (
        query_section in available and query_section != saved_section
    ):
        st.session_state[SUBMITTED_QUERY_STATE_KEY] = ""
    st.session_state[ACTIVE_SECTION_STATE_KEY] = active["id"]
    return active


def _clear_report_search() -> None:
    st.session_state[SEARCH_DRAFT_STATE_KEY] = ""
    st.session_state[SUBMITTED_QUERY_STATE_KEY] = ""


def _render_search(reader: dict[str, Any], language: str) -> tuple[dict[str, str], ...] | None:
    submitted_query = str(st.session_state.get(SUBMITTED_QUERY_STATE_KEY, ""))
    with st.container(key="final-report-search-shell"):
        with st.form("final-report-search", clear_on_submit=False):
            st.text_input(
                t("搜索完整报告", "Search the full report"),
                placeholder=t("输入关键词，例如：基线、参数、稳健性", "Enter a keyword, e.g. baseline, parameter, robustness"),
                key=SEARCH_DRAFT_STATE_KEY,
            )
            search_column, clear_column, _ = st.columns((1, 1.35, 5), gap="small")
            with search_column:
                submitted = st.form_submit_button(t("搜索", "Search"))
            with clear_column:
                cleared = st.form_submit_button(t("清除搜索", "Clear search"), on_click=_clear_report_search)
    if cleared:
        return None
    if submitted:
        submitted_query = str(st.session_state.get(SEARCH_DRAFT_STATE_KEY, "")).strip()
        st.session_state[SUBMITTED_QUERY_STATE_KEY] = submitted_query

    if not submitted_query:
        return None
    matches = filter_report_sections(reader["sections"], submitted_query)
    assert isinstance(matches, tuple)
    if not matches:
        st.info(t("没有找到匹配章节，请尝试其他关键词。", "No matching section was found. Try another keyword."))
        return tuple()

    st.caption(t(f"找到 {len(matches)} 个匹配章节", f"{len(matches)} matching sections"))
    cards = "".join(
        f'<a class="report-search-result" href="{html.escape(_report_section_href(match["id"], language, clear_search=True), quote=True)}">'
        f'<strong>{html.escape(match["title"])}</strong><span>{html.escape(match["snippet"])}</span></a>'
        for match in matches
    )
    render_html(f'<div class="report-search-results">{cards}</div>', localize=False)
    return matches


def render_final_report_page() -> None:
    """Render the current report chapter and a submit-only cross-report search."""
    render_route_nav("doc")
    language = get_ui_language()
    report_path = get_report_path(language)

    try:
        modified_ns = report_path.stat().st_mtime_ns
        reader = load_embeddable_report(str(report_path), modified_ns)
        active_section = _get_active_section(reader)
    except (OSError, UnicodeError, ValueError) as exc:
        st.error(t(f"无法读取报告：{exc}", f"Unable to read the report: {exc}"))
        return

    report_language = "zh-CN" if language == "zh" else "en"
    if reader["intro_html"]:
        render_html(
            f'<div id="report-top" class="native-report-shell native-report-intro" lang="{report_language}">'
            f'{reader["intro_html"]}</div>',
            localize=False,
        )

    matches = _render_search(reader, language)
    if matches is not None:
        return

    toc_html = render_report_toc(reader, language, active_section=active_section["id"])
    navigation_markup = build_report_navigation(
        reader["toc_html"],
        language,
        active_section=active_section["id"],
        anchor_to_section=reader["anchor_to_section"],
    )
    top_label = t("回到顶部", "Back to top")
    with performance_span("report", "render_section", section=active_section["id"]):
        render_html(
            f'<div class="native-report-shell native-report-reading" lang="{report_language}">'
            f'{navigation_markup}<div class="report-reading-document">{toc_html}{active_section["html"]}</div>'
            f'<a class="report-back-top" href="#report-top" aria-label="{top_label}" title="{top_label}">↑</a></div>',
            localize=False,
        )
        render_html(
            build_report_interaction_script(),
            localize=False,
            unsafe_allow_javascript=True,
        )
