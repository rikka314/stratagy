import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import { Status } from '../components/Primitives'
import { useAsync } from '../hooks/useAsync'
import { useApp } from '../state/AppContext'
import './HomePage.css'

const FALLBACK_NEWS = {
  zh: [
    '微软创 2008 年以来最佳单日表现，科技股重新领涨美股。',
    'AMD 财报进入焦点，数据中心需求成为半导体估值的新锚。',
    '通胀担忧仍压在债券市场上，长端利率继续牵动成长股定价。',
    'AI 资本开支越过高峰后，市场开始追问：收入何时跟上投入？',
  ],
  en: [
    'Microsoft posts its best day since 2008 as technology stocks retake the lead.',
    'AMD earnings move into focus as data-center demand resets the chip valuation debate.',
    'Inflation anxiety lingers in bonds, keeping long-term yields at the center of growth-stock pricing.',
    'After the AI spending surge, markets are asking when revenue will catch up with investment.',
  ],
}

const quoteTone = (value) => value == null ? '' : value >= 0 ? 'is-up' : 'is-down'
const formatPct = (value) => value == null ? '—' : `${value > 0 ? '+' : ''}${Number(value).toFixed(2)}%`
const formatPrice = (value) => value == null ? '—' : Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 })

function MiniCandles({ rows, label }) {
  const model = useMemo(() => {
    if (!Array.isArray(rows) || rows.length < 2) return null
    const values = rows.flatMap((row) => [row.low, row.high]).map(Number).filter(Number.isFinite)
    if (!values.length) return null
    const low = Math.min(...values)
    const high = Math.max(...values)
    const span = Math.max(high - low, Math.max(Math.abs(high), 1) * 0.002)
    const y = (value) => 7 + ((high + span * 0.08 - value) / (span * 1.16)) * 86
    const step = 440 / rows.length
    return rows.map((row, index) => {
      const open = Number(row.open); const close = Number(row.close)
      const candleHigh = Number(row.high); const candleLow = Number(row.low)
      if (![open, close, candleHigh, candleLow].every(Number.isFinite)) return null
      return { x: (index + 0.5) * step, open: y(open), close: y(close), high: y(candleHigh), low: y(candleLow), up: close >= open, width: Math.max(4, Math.min(10, step * 0.52)) }
    }).filter(Boolean)
  }, [rows])
  if (!model) return <div className="home-candles-empty">{label}</div>
  return <svg className="home-candles" viewBox="0 0 440 104" role="img" aria-label={label} preserveAspectRatio="none">
    {[7, 50, 93].map((lineY) => <line key={lineY} x1="0" x2="440" y1={lineY} y2={lineY} className="home-candle-grid" />)}
    {model.map((item, index) => <g key={index} className={item.up ? 'is-up' : 'is-down'}>
      <line x1={item.x} x2={item.x} y1={item.high} y2={item.low} />
      <rect x={item.x - item.width / 2} y={Math.min(item.open, item.close)} width={item.width} height={Math.max(2, Math.abs(item.close - item.open))} />
    </g>)}
  </svg>
}

function MarketTemperature({ indices, zh }) {
  const available = indices.filter((item) => Number.isFinite(Number(item.pct_change)))
  const changes = available.map((item) => Number(item.pct_change))
  const positive = changes.filter((value) => value > 0).length
  const average = changes.length ? changes.reduce((sum, value) => sum + value, 0) / changes.length : 0
  const dispersion = changes.length ? Math.sqrt(changes.reduce((sum, value) => sum + (value - average) ** 2, 0) / changes.length) : 0
  const tone = average > 0.45 ? 'warm' : average < -0.45 ? 'cool' : 'balanced'
  const word = zh ? ({ warm: '偏暖', cool: '偏冷', balanced: '平衡' })[tone] : ({ warm: 'WARM', cool: 'COOL', balanced: 'BALANCED' })[tone]
  const summary = zh ? ({ warm: '主要指数整体偏强，风险偏好回升。', cool: '主要指数整体承压，风险偏好趋弱。', balanced: '主要指数方向分化，市场保持均衡。' })[tone] : ({ warm: 'Major indices are broadly firm as risk appetite improves.', cool: 'Major indices are under pressure as risk appetite softens.', balanced: 'Major indices are mixed and the market remains balanced.' })[tone]
  return <div className={`home-temperature-body is-${tone}`}>
    <div className="home-temperature-statement"><strong>{word}</strong><span>{summary}</span></div>
    <dl className="home-temperature-metrics">
      <div><dt>{zh ? '上涨指数' : 'Indices up'}</dt><dd>{positive}/{available.length}</dd></div>
      <div><dt>{zh ? '平均涨跌' : 'Average'}</dt><dd>{average > 0 ? '+' : ''}{average.toFixed(2)}%</dd></div>
      <div><dt>{zh ? '市场离散' : 'Dispersion'}</dt><dd>{dispersion.toFixed(2)} pt</dd></div>
    </dl>
  </div>
}

export function HomePage() {
  const { language } = useApp()
  const zh = language === 'zh'
  const [selectedMarket, setSelectedMarket] = useState('US')
  const [focusIndex, setFocusIndex] = useState(0)
  const market = useAsync(() => api.homeMarket(), [], true)
  const news = useAsync(() => api.homeNews(language), [language], true)
  const recommendations = useAsync(() => api.homeRecommendations(selectedMarket), [selectedMarket], true)
  const stockPool = recommendations.data?.items || []
  const focus = stockPool.length ? stockPool[focusIndex % stockPool.length] : null
  const candles = useAsync(() => focus ? api.homeCandles(selectedMarket, focus.symbol) : Promise.resolve({ candles: [] }), [selectedMarket, focus?.symbol], true)
  const indices = market.data?.indices || []
  const headlines = news.data?.headlines?.map((item) => item.title).filter(Boolean) || FALLBACK_NEWS[language]

  useEffect(() => { setFocusIndex(0) }, [selectedMarket])

  return <main id="main" className="home-original" aria-labelledby="market-platform-title">
    <section className="home-identity">
      <h1 id="market-platform-title">{zh ? '股票策略分析平台' : 'Stock Strategy Analysis Platform'}</h1>
      <div className="home-news-ticker" role="region" aria-label={zh ? '最新股票新闻' : 'Latest stock-market news'}>
        {headlines.slice(0, 4).map((headline, index) => <span key={`${language}-${headline}`} style={{ '--news-delay': `${index * 6 - .4}s` }}>{headline}</span>)}
      </div>
    </section>

    <section className="home-stock-cloud" aria-label={zh ? '近期强势股票' : 'Recent strong stocks'}>
      {recommendations.status === 'loading' && !focus && <Status state="loading">{zh ? '正在加载最新市场数据' : 'Loading latest market data'}</Status>}
      {recommendations.status === 'error' && !focus && <Status state="error" onRetry={recommendations.run}>{zh ? '推荐股票暂不可用' : 'Recommendations unavailable'}</Status>}
      {focus && <>
        <article className={`home-stock-focus ${quoteTone(focus.pct_change)}`}>
          <span className="home-stock-eyebrow">{zh ? '单股分析推荐 · 日 K' : 'Single-stock recommendations · daily candles'}</span>
          <strong className="home-stock-company">{zh ? focus.name_zh : focus.name_en}</strong>
          <div className="home-stock-line"><span>{focus.symbol} · {selectedMarket === 'US' ? (zh ? '美股' : 'US') : (zh ? 'A 股' : 'CN A')}</span><b>{formatPct(focus.pct_change)}</b></div>
          <MiniCandles rows={candles.data?.candles || []} label={candles.status === 'loading' ? (zh ? '正在加载日 K' : 'Loading daily candles') : candles.status === 'error' ? (zh ? 'K 线暂不可用' : 'Candles unavailable') : (zh ? '近 20 个交易日日 K' : 'Last 20 sessions · daily candles')} />
        </article>
        {stockPool.filter((_, index) => index !== focusIndex % stockPool.length).slice(0, 4).map((item, index) => <span key={item.symbol} className={`home-stock-orbit slot-${index + 1} ${quoteTone(item.pct_change)}`}>
          <strong>{zh ? item.name_zh : item.name_en}</strong><small>{item.symbol}</small><span>{formatPct(item.pct_change)}</span>
        </span>)}
      </>}
    </section>

    <div className="home-stock-controls" aria-label={zh ? '首页股票控件' : 'Homepage stock controls'}>
      <button className={selectedMarket === 'US' ? 'active' : ''} onClick={() => setSelectedMarket('US')}>{zh ? '美股' : 'US'}</button>
      <button className={selectedMarket === 'CN_A' ? 'active' : ''} onClick={() => setSelectedMarket('CN_A')}>{zh ? 'A 股' : 'CN A'}</button>
      <button onClick={() => setFocusIndex((index) => stockPool.length ? (index + 1) % stockPool.length : 0)} disabled={!stockPool.length}>{zh ? '换一只 ↗' : 'Next ↗'}</button>
    </div>

    <section className="home-market-lens" aria-label={zh ? '市场实时概览' : 'Live market overview'}>
      {market.status === 'error' && <Status state="error" onRetry={market.run}>{zh ? '行情暂不可用' : 'Quotes unavailable'}</Status>}
      <article className="home-lens-scene scene-indices">
        <header><span>{zh ? '01 / 双市场指数' : '01 / MARKET INDICES'}</span><strong>{zh ? '先判断市场，再进入个股。' : 'Read the market before the stock.'}</strong></header>
        <div className="home-index-strip">{indices.map((item) => <div key={item.symbol} className={quoteTone(item.pct_change)}><span>{zh ? item.region_zh : item.region_en}</span><strong>{zh ? item.name_zh : item.name_en}</strong><b>{formatPrice(item.price)}</b><small>{formatPct(item.pct_change)}</small></div>)}</div>
      </article>
      <article className="home-lens-scene scene-leaders">
        <header><span>{zh ? '02 / 单股推荐观察' : '02 / SINGLE-STOCK RECOMMENDATIONS'}</span><strong>{zh ? '与单股分析入口使用同一推荐来源。' : 'The same recommendation feed as the Single Stock entry.'}</strong></header>
        <div className="home-leader-list">{stockPool.map((item, index) => <div key={item.symbol} className={quoteTone(item.pct_change)}><span>{String(index + 1).padStart(2, '0')}</span><strong>{item.symbol}<small>{zh ? item.name_zh : item.name_en}</small></strong><em>{zh ? item.region_zh : item.region_en}</em><b>{formatPrice(item.price)}</b><i>{formatPct(item.pct_change)}</i></div>)}</div>
      </article>
      <article className="home-lens-scene scene-temperature">
        <header><span>{zh ? '03 / 市场温度' : '03 / MARKET TEMPERATURE'}</span><strong>{zh ? '把分散报价压缩成一个市场读数。' : 'Compress the tape into one market read.'}</strong></header>
        <MarketTemperature indices={indices} zh={zh} />
      </article>
      <div className="home-lens-progress" aria-hidden="true"><i /><i /><i /></div>
    </section>
  </main>
}
