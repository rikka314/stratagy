"""
首页模块
========
"""

from __future__ import annotations

import streamlit as st

from ui.theme import render_html, render_route_nav, route_href


def render_home_page() -> None:
    """渲染 `/strategy` 首页。"""
    render_route_nav("home")

    render_html(
        f"""
<section class="hero-shell">
  <div class="hero-copy-column">
    <div class="page-kicker">Strategy Research Site</div>
    <h1 class="hero-title">把股票策略入口做成真正的网站首页。</h1>
    <p class="hero-copy">
      这个站点先用市场上下文和清楚的入口动作建立研究方向，再把你送进原有单股或多股分析链路。
      目标不是把更多面板堆上来，而是让研究路径一眼就能看懂。
    </p>

    <div class="action-card">
      <div class="action-card-kicker">Choose A Route</div>
      <h2 class="action-card-title">先定研究路径，再进入分析主界面</h2>
      <p class="action-card-copy">
        单股模式适合围绕一个标的持续展开， 多股模式适合先组织股票池再看横向比较、
        组合结果和后续策略摘要。
      </p>
      <div class="cta-row">
        <a class="cta-link" href="{route_href('stock-analysis')}">进入单股分析</a>
        <a class="cta-link secondary" href="{route_href('stocks-analysis')}">进入多股分析</a>
      </div>
    </div>

    <div class="hero-note-list">
      <div class="hero-note-item"><strong>01</strong><span>先看市场上下文，再决定这次研究到底从哪只股票或哪组股票开始。</span></div>
      <div class="hero-note-item"><strong>02</strong><span>搜索、上传和推荐入口都保持在同一条页面语法里，不把用户推回后台式操作区。</span></div>
      <div class="hero-note-item"><strong>03</strong><span>主分析页逻辑不变，变化的是入口节奏、视觉层级和网站感。</span></div>
    </div>
  </div>

  <div class="showcase-board home-showcase">
    <div class="board-chip">Live Product View</div>

    <div class="home-showcase-grid">
      <div class="floating-sheet sheet-market">
        <div class="floating-sheet-title">市场上下文</div>
        <div class="floating-sheet-copy">指数快照和推荐入口固定留在右侧，让研究先从背景判断开始，再进入具体入口动作。</div>
        <div class="board-micro-list">
          <div class="board-micro-item"><span>US</span><strong>纳指 / 标普 / 道指</strong></div>
          <div class="board-micro-item"><span>A</span><strong>上证 / 深成 / 创业板</strong></div>
        </div>
        <div class="board-flow-row compact">
          <span>实时推荐</span>
          <span>搜索直达</span>
        </div>
      </div>

      <div class="home-showcase-stack">
        <div class="floating-sheet sheet-workflow">
          <div class="floating-sheet-title">策略流程</div>
          <div class="floating-sheet-copy">入口页只建立上下文，真正的参数、工作流和 artifact 仍在分析页继续。</div>
        </div>

        <div class="floating-sheet sheet-progress">
          <div class="floating-sheet-title">研究状态</div>
          <div class="floating-sheet-copy">当前站点已经具备单股与多股两条真实路由，入口和主分析页顺序一致。</div>
        </div>
      </div>
    </div>

    <div class="board-main-sheet">
      <div class="action-card-kicker">Research Rail</div>
      <h3>市场上下文 → 入口动作 → 主分析页</h3>
      <p>
        左侧负责叙事和主 CTA，右侧用一个大展示板说明这个工具怎么被使用。
        单股与多股都走同一套路由壳层，页面看起来像产品，而不是一组面板。
      </p>
      <div class="board-flow-row">
        <span>市场快照</span>
        <span>搜索或上传</span>
        <span>推荐入口</span>
        <span>进入分析</span>
      </div>
      <p class="board-footnote">推荐入口已经并入主流程，不再单独长出一块漂浮面板。</p>
    </div>
  </div>
</section>
        """
    )

    render_html(
        f"""
<section class="support-columns">
  <div class="support-block">
    <h3>单股研究</h3>
    <p>更适合围绕一个标的查看行情、生成策略、比较模型和解释信号。</p>
    <div class="support-cta-row">
      <a class="cta-link secondary pill-secondary" href="{route_href('model-evaluation')}">进入模型评估</a>
    </div>
  </div>
  <div class="support-block">
    <h3>多股比较</h3>
    <p>更适合先整理股票池，再进入横向比较、组合模拟和策略级摘要。</p>
  </div>
  <div class="support-block">
    <h3>统一节奏</h3>
    <p>首页和入口页先负责建立研究背景，主分析页继续承接原有工作流，不重复造第二套逻辑。</p>
  </div>
</section>
        """
    )
