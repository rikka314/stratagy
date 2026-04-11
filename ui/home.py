"""
首页模块
========
"""

from __future__ import annotations

from ui.i18n import tr
from ui.theme import render_html, render_route_nav, route_href


def render_home_page() -> None:
    """page.strategy.home.description"""
    render_route_nav("home")

    hero_notes_markup = "".join(
        f"<div class='hero-note-item'><strong>{index:02d}</strong><span>{tr(key)}</span></div>"
        for index, key in enumerate(
            [
                "home.hero.note.1",
                "home.hero.note.2",
                "home.hero.note.3",
            ],
            start=1,
        )
    )
    board_flow_markup = "".join(
        f"<span>{tr(key)}</span>"
        for key in [
            "home.board.flow.market",
            "home.board.flow.searchOrUpload",
            "home.board.flow.recommendation",
            "home.board.flow.enterAnalysis",
        ]
    )

    render_html(
        f"""
<section class="hero-shell">
  <div class="hero-copy-column">
    <div class="page-kicker">{tr("home.hero.kicker")}</div>
    <h1 class="hero-title">{tr("home.hero.title")}</h1>
    <p class="hero-copy">{tr("home.hero.copy")}</p>

    <div class="action-card">
      <div class="action-card-kicker">{tr("home.route.kicker")}</div>
      <h2 class="action-card-title">{tr("home.route.title")}</h2>
      <p class="action-card-copy">{tr("home.route.copy")}</p>
      <div class="cta-row">
        <a class="cta-link" href="{route_href('stock-analysis')}">{tr("home.cta.single")}</a>
        <a class="cta-link secondary" href="{route_href('stocks-analysis')}">{tr("home.cta.multi")}</a>
      </div>
    </div>

    <div class="hero-note-list">{hero_notes_markup}</div>
  </div>

  <div class="showcase-board home-showcase">
    <div class="board-chip">{tr("home.showcase.kicker")}</div>

    <div class="home-showcase-grid">
      <div class="floating-sheet sheet-market">
        <div class="floating-sheet-title">{tr("home.market.title")}</div>
        <div class="floating-sheet-copy">{tr("home.market.copy")}</div>
        <div class="board-micro-list">
          <div class="board-micro-item"><span>US</span><strong>{tr("home.market.us")}</strong></div>
          <div class="board-micro-item"><span>A</span><strong>{tr("home.market.cn")}</strong></div>
        </div>
        <div class="board-flow-row compact">
          <span>{tr("home.market.liveRecommendation")}</span>
          <span>{tr("home.market.directSearch")}</span>
        </div>
      </div>

      <div class="home-showcase-stack">
        <div class="floating-sheet sheet-workflow">
          <div class="floating-sheet-title">{tr("home.workflow.title")}</div>
          <div class="floating-sheet-copy">{tr("home.workflow.copy")}</div>
        </div>

        <div class="floating-sheet sheet-progress">
          <div class="floating-sheet-title">{tr("home.progress.title")}</div>
          <div class="floating-sheet-copy">{tr("home.progress.copy")}</div>
        </div>
      </div>
    </div>

    <div class="board-main-sheet">
      <div class="action-card-kicker">{tr("home.board.kicker")}</div>
      <h3>{tr("home.board.title")}</h3>
      <p>{tr("home.board.copy")}</p>
      <div class="board-flow-row">{board_flow_markup}</div>
      <p class="board-footnote">{tr("home.board.footnote")}</p>
    </div>
  </div>
</section>
        """
    )

    render_html(
        f"""
<section class="support-columns">
  <div class="support-block">
    <h3>{tr("home.support.single.title")}</h3>
    <p>{tr("home.support.single.copy")}</p>
    <div class="support-cta-row">
      <a class="cta-link secondary pill-secondary" href="{route_href('model-evaluation')}">{tr("home.support.single.cta")}</a>
    </div>
  </div>
  <div class="support-block">
    <h3>{tr("home.support.multi.title")}</h3>
    <p>{tr("home.support.multi.copy")}</p>
  </div>
  <div class="support-block">
    <h3>{tr("home.support.unified.title")}</h3>
    <p>{tr("home.support.unified.copy")}</p>
  </div>
</section>
        """
    )
