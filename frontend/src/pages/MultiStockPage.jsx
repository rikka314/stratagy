import { useEffect, useRef, useState } from 'react'
import { Download, Plus, RefreshCw, Trash2, Upload } from 'lucide-react'
import { api } from '../api/client'
import { LineChart } from '../components/Charts'
import { Button, DataTable, Field, Metric, Status } from '../components/Primitives'
import { useAsync } from '../hooks/useAsync'
import { useApp } from '../state/AppContext'
import './multi-stock.css'
import { StockSearch } from '../components/StockSearch'

const BASIC_VIEWS = ['comparison', 'relative_strength', 'risk_return', 'factor_score', 'correlation']

export function MultiStockPage() {
  const { language, workspace, addDataset, setPortfolio, setWorkspace } = useApp()
  const zh = language === 'zh'; const draft = workspace.multiDraft || {}
  const [market, setMarket] = useState(draft.market || 'US'); const [query, setQuery] = useState('')
  const [selected, setSelected] = useState(draft.selected || []); const [weights, setWeights] = useState(draft.weights || {})
  const [params, setParams] = useState(draft.params || {}); const [adjust, setAdjust] = useState(draft.adjust || 'qfq')
  const [startDate, setStartDate] = useState(draft.startDate || ''); const [endDate, setEndDate] = useState(draft.endDate || '')
  const [analysisStarted, setAnalysisStarted] = useState(Boolean(draft.analysisStarted || workspace.portfolio))
  const [analysisTab, setAnalysisTab] = useState('basics'); const [basicView, setBasicView] = useState('comparison')
  const [analyses, setAnalyses] = useState({}); const [analysisError, setAnalysisError] = useState('')
  const [factorScores, setFactorScores] = useState(null); const [factorError, setFactorError] = useState('')
  const [detailsOpen, setDetailsOpen] = useState(false); const [trials, setTrials] = useState(30)
  const [snapshotRefresh, setSnapshotRefresh] = useState(0)
  const [result, setResult] = useState(workspace.portfolio?.result || null); const [lastPayload, setLastPayload] = useState(workspace.portfolio?.request || null)
  const [error, setError] = useState(''); const [busy, setBusy] = useState(false); const [optimization, setOptimization] = useState(null)
  const fileRef = useRef(null)
  const marketRef = useRef(market)
  const metadata = useAsync(() => api.metadata(), [], true); const marketSnapshot = useAsync(() => api.marketContext(market, snapshotRefresh > 0), [market, snapshotRefresh], true)
  const recommendations = useAsync(() => api.homeRecommendations(market), [market], true)
  const persistedId = workspace.portfolio?.result_id

  useEffect(() => { if (!persistedId || result) return; let active = true; api.portfolioResult(persistedId).then(v => { if (active) setResult(v) }).catch(e => { if (active) setError(e.message) }); return () => { active = false } }, [persistedId, result])
  useEffect(() => { if (metadata.data?.defaults) setParams(old => ({ ...metadata.data.defaults, ...old })) }, [metadata.data])
  useEffect(() => { marketRef.current = market }, [market])
  useEffect(() => { setWorkspace(old => ({ ...old, multiDraft: { market, selected, weights, params, adjust, startDate, endDate, analysisStarted } })) }, [market, selected, weights, params, adjust, startDate, endDate, analysisStarted, setWorkspace])
  useEffect(() => {
    if (!result || !lastPayload) return
    const current = selected.map(item => item.dataset_id).sort().join('|'); const computed = [...(lastPayload.dataset_ids || [])].sort().join('|')
    if (current !== computed) { setResult(null); setLastPayload(null); setPortfolio(null) }
  }, [selected, result, lastPayload, setPortfolio])
  useEffect(() => {
    if (!analysisStarted || analysisTab !== 'basics' || !selected.length) return
    let active = true; setAnalysisError('')
    Promise.all(selected.map(item => api.datasetAnalysis(item.dataset_id, { params }).then(value => [item.symbol, value])))
      .then(entries => { if (active) setAnalyses(Object.fromEntries(entries)) })
      .catch(cause => { if (active) setAnalysisError(cause.message) })
    return () => { active = false }
  }, [analysisStarted, analysisTab, selected, params])
  useEffect(() => {
    if (!analysisStarted || analysisTab !== 'basics' || basicView !== 'factor_score' || !selected.length) return
    let active = true; setFactorScores(null); setFactorError('')
    api.portfolioFactors({ dataset_ids: selected.map(item => item.dataset_id), params })
      .then(value => { if (active) setFactorScores(value) })
      .catch(cause => { if (active) setFactorError(cause.message) })
    return () => { active = false }
  }, [analysisStarted, analysisTab, basicView, selected, params])

  const addSymbol = async item => {
    if (busy || selected.some(row => row.symbol === item.symbol) || selected.length >= 20) return
    setBusy(true); setError('')
    const requestedMarket = market
    try { const data = await api.loadStock({ market: requestedMarket, symbol: item.symbol, adjust, start_date: startDate || null, end_date: endDate || null }); if (marketRef.current !== requestedMarket) return; addDataset(data); const { candles, ...summary } = data; setSelected(rows => [...rows, summary]); setWeights(old => ({ ...old, [data.dataset_id]: 1 })) }
    catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  const uploadFiles = async files => {
    setBusy(true); setError('')
    const requestedMarket = market
    for (const file of files.slice(0, 20 - selected.length)) { const symbol = file.name.replace(/\.csv$/i, ''); if (selected.some(row => row.symbol === symbol)) continue; try { let data = await api.uploadStock(file, { market: requestedMarket, symbol, adjust }); if (startDate || endDate) data = await api.sliceDataset(data.dataset_id, { start_date: startDate || null, end_date: endDate || null }); if (marketRef.current !== requestedMarket) return; addDataset(data); const { candles, ...summary } = data; setSelected(rows => rows.some(row => row.symbol === data.symbol) ? rows : [...rows, summary]); setWeights(old => ({ ...old, [data.dataset_id]: 1 })) } catch (e) { setError(e.message) } }
    if (fileRef.current) fileRef.current.value = ''; setBusy(false)
  }
  const removeSymbol = item => { setSelected(rows => rows.filter(row => row.dataset_id !== item.dataset_id)); setWeights(old => { const next = { ...old }; delete next[item.dataset_id]; return next }); if (selected.length <= 2) { setAnalysisStarted(false); setResult(null) } }
  const makePayload = (equalWeight = false) => { if (selected.length < 2) throw new Error(zh ? '请选择至少两只股票。' : 'Select at least two stocks.'); const raw = selected.map(item => equalWeight ? 1 : Number(weights[item.dataset_id] ?? 1)); const total = raw.reduce((a, b) => a + b, 0); if (raw.some(v => !Number.isFinite(v) || v < 0) || !Number.isFinite(total) || total <= 0) throw new Error(zh ? '权重必须为非负数，且总和大于零。' : 'Use non-negative weights with a positive finite total.'); return { dataset_ids: selected.map(item => item.dataset_id), weights: Object.fromEntries(selected.map((item, i) => [item.dataset_id, raw[i] / total])), params } }
  const startAnalysis = () => { if (selected.length < 2) { setError(zh ? '至少选择或上传两只股票。' : 'Select or upload at least two stocks.'); return } setError(''); setAnalysisStarted(true); setAnalysisTab('basics'); window.scrollTo({ top: 0, behavior: 'smooth' }) }
  const run = async () => { setBusy(true); setError(''); try { const payload = makePayload(); const next = await api.portfolio(payload); setResult(next); setLastPayload(payload); setPortfolio({ result: next, request: payload, result_id: next.result_id }) } catch (e) { setError(e.message) } finally { setBusy(false) } }
  const optimize = async () => { setBusy(true); setError(''); try { const payload = makePayload(true); const best = await api.optimizePortfolio({ ...payload, n_trials: Number(trials) }); const updated = { ...params, ...Object.fromEntries(Object.entries(best).filter(([key]) => key in params)) }; const finalPayload = { ...payload, params: updated }; const next = await api.portfolio(finalPayload); setParams(updated); setWeights(Object.fromEntries(selected.map(item => [item.dataset_id, 1]))); setOptimization(best); setResult(next); setLastPayload(finalPayload); setPortfolio({ result: next, request: finalPayload, result_id: next.result_id }) } catch (e) { setError(e.message) } finally { setBusy(false) } }
  const download = async () => { setBusy(true); setError(''); try { if (!lastPayload) throw new Error(zh ? '请先运行组合分析。' : 'Run the portfolio analysis first.'); const html = await api.exportPortfolio(lastPayload, language); const url = URL.createObjectURL(new Blob([html], { type: 'text/html' })); const anchor = document.createElement('a'); anchor.href = url; anchor.download = 'portfolio-report.html'; anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000) } catch (e) { setError(e.message) } finally { setBusy(false) } }
  const marketItems = marketSnapshot.data?.indices || []

  if (!analysisStarted) return <EntryPage {...{ zh, market, setMarket, query, setQuery, selected, setSelected, setWeights, adjust, setAdjust, startDate, setStartDate, endDate, setEndDate, addSymbol, uploadFiles, removeSymbol, fileRef, busy, error, startAnalysis, marketItems, marketSnapshot, recommendations, setSnapshotRefresh }} />
  return <AnalysisPage {...{ zh, market, selected, analyses, analysisError, factorScores, factorError, weights, setWeights, detailsOpen, setDetailsOpen, analysisTab, setAnalysisTab, basicView, setBasicView, params, setParams, result, busy, error, run, trials, setTrials, optimize, optimization, download, setAnalysisStarted }} />
}

function EntryPage({ zh, market, setMarket, query, setQuery, selected, setSelected, setWeights, adjust, setAdjust, startDate, setStartDate, endDate, setEndDate, addSymbol, uploadFiles, removeSymbol, fileRef, busy, error, startAnalysis, marketItems, marketSnapshot, recommendations, setSnapshotRefresh }) {
  const changeMarket = value => { setMarket(value); setQuery(''); setSelected([]); setWeights({}) }
  return <main id="main" className="page multi-page multi-entry">
    <header className="multi-intro"><p>{zh ? '多股分析' : 'Multi-stock analysis'}</p><h1>{zh ? '多股对比分析' : 'Compare multiple stocks'}</h1></header>
    <div className="multi-entry-grid"><section className="multi-action-panel"><h2>{zh ? '选择股票' : 'Select stocks'}</h2>
      <div className="multi-market-toggle" role="radiogroup">{['US', 'CN_A'].map(value => <button key={value} disabled={busy} role="radio" aria-checked={market === value} onClick={() => changeMarket(value)}>{value === 'US' ? (zh ? '美股' : 'US stocks') : (zh ? 'A 股' : 'China A-shares')}</button>)}</div>
      <div className="multi-block"><h3>{zh ? '数据设置' : 'Data settings'}</h3><div className="multi-entry-fields"><Field label={zh ? '复权方式' : 'Adjustment'}><select value={adjust} onChange={e => setAdjust(e.target.value)}><option value="qfq">{zh ? '前复权' : 'Forward adjusted'}</option><option value="hfq">{zh ? '后复权' : 'Backward adjusted'}</option><option value="none">{zh ? '不复权' : 'Unadjusted'}</option></select></Field><Field label={zh ? '起始日期' : 'Start date'}><input type="date" value={startDate} onChange={e => setStartDate(e.target.value)} /></Field><Field label={zh ? '结束日期' : 'End date'}><input type="date" value={endDate} onChange={e => setEndDate(e.target.value)} /></Field></div></div>
      <div className="multi-block"><h3>{zh ? '搜索并加入股票' : 'Search and add stocks'}</h3><StockSearch zh={zh} market={market} query={query} onQueryChange={setQuery} disabled={busy} isSelected={item=>selected.some(row=>row.symbol===item.symbol)} onSelect={item=>{setQuery('');addSymbol(item)}}/></div>
      <div className="multi-block"><div className="multi-block-heading"><h3>{zh ? '上传多个 CSV' : 'Upload multiple CSV files'}</h3><span title="date, open, high, low, close, volume">CSV ?</span></div><input ref={fileRef} type="file" accept=".csv" multiple hidden onChange={e => uploadFiles([...e.target.files])} /><Button disabled={busy} variant="secondary" onClick={() => fileRef.current?.click()}><Upload size={16} />{zh ? '选择 CSV 文件' : 'Choose CSV files'}</Button></div>
      <div className="multi-block"><h3>{zh ? `当前已选股票（${selected.length}）` : `Selected stocks (${selected.length})`}</h3><div className="multi-row-sheet">{selected.length ? selected.map(item => <div className="multi-selected-row" key={item.dataset_id}><span><strong>{item.symbol}</strong><small>{item.source === 'upload' ? (zh ? '上传数据' : 'Uploaded data') : (zh ? '市场数据' : 'Market data')}</small></span><button onClick={() => removeSymbol(item)}><Trash2 size={14} />{zh ? '移除' : 'Remove'}</button></div>) : <p className="caption">{zh ? '至少选择两只股票后开始分析。' : 'Select at least two stocks to begin.'}</p>}</div></div>
      {error && <Status state="error">{error}</Status>}<Button className="multi-start" disabled={busy || selected.length < 2} onClick={startAnalysis}>{zh ? '开始多股分析' : 'Start multi-stock analysis'}</Button>
    </section><aside className="multi-showcase"><p className="multi-kicker">{zh ? '市场展示板' : 'Market showcase'}</p><h2>{zh ? '市场快照与推荐入口' : 'Market snapshot and recommendations'}</h2><div className="multi-showcase-heading"><h3>{zh ? '市场快照' : 'Market snapshot'}</h3><button disabled={marketSnapshot.status === 'loading'} onClick={() => setSnapshotRefresh(value => value + 1)}><RefreshCw size={14} />{zh ? '刷新市场快照' : 'Refresh'}</button></div><div className="multi-snapshot-grid">{marketItems.length ? marketItems.map((item, i) => <div key={item.symbol || item.label || i}><span>{item.label || item.name || item.symbol || '—'}</span><strong>{item.close_text || item.close || item.value || 'N/A'}</strong><small className={String(item.pct_text || '').startsWith('-') ? 'negative' : 'positive'}>{item.pct_text || item.change || ''}</small></div>) : <Status>{zh ? '市场快照暂不可用' : 'Market snapshot unavailable'}</Status>}</div><p className="caption">{zh ? `推荐来源：${marketSnapshot.data?.recommendation_source || '市场上下文观察池'}` : `Source: ${marketSnapshot.data?.recommendation_source || 'market context watchlist'}`}</p><div className="multi-recommend-sheet" role="region" tabIndex={0} aria-label={zh ? '推荐股票，可滚动' : 'Recommended stocks, scrollable'}><h3>{zh ? '推荐股票' : 'Recommended stocks'}</h3>{((marketSnapshot.data?.recommendations?.length ? marketSnapshot.data.recommendations : recommendations.data?.items) || []).slice(0, 8).map(item => <PickerRow key={item.symbol} item={item} zh={zh} disabled={busy || selected.some(row => row.symbol === item.symbol)} onAdd={() => addSymbol(item)} />)}</div></aside></div>
  </main>
}

function PickerRow({ item, zh, disabled, onAdd }) { return <div className="multi-picker-row"><span><strong>{item.symbol}{item.name ? ` · ${item.name}` : ''}</strong><small>{item.pct_text || item.change_text || ''}</small></span><button disabled={disabled} onClick={onAdd}><Plus size={14} />{zh ? '加入' : 'Add'}</button></div> }

function AnalysisPage({ zh, market, selected, analyses, analysisError, factorScores, factorError, weights, setWeights, detailsOpen, setDetailsOpen, analysisTab, setAnalysisTab, basicView, setBasicView, params, setParams, result, busy, error, run, trials, setTrials, optimize, optimization, download, setAnalysisStarted }) {
  const dates = selected.flatMap(item => [formatDate(item.date_range?.start), formatDate(item.date_range?.end)]).filter(Boolean).sort(); const individual = Object.entries(result?.individual || {}).map(([symbol, row]) => ({ symbol, weight: result.weights?.[symbol], ...Object.fromEntries(Object.entries(row).filter(([, value]) => value == null || typeof value !== 'object')) }))
  const labels = { total_return: zh ? '组合总收益' : 'Portfolio return', sharpe: zh ? '组合夏普' : 'Portfolio Sharpe', max_drawdown: zh ? '组合最大回撤' : 'Portfolio max drawdown', benchmark_total_return: zh ? '买入持有收益' : 'Buy-and-hold return', benchmark_sharpe: zh ? '买入持有夏普' : 'Buy-and-hold Sharpe', benchmark_max_drawdown: zh ? '买入持有回撤' : 'Buy-and-hold drawdown' }
  return <main id="main" className="page multi-page multi-analysis"><header className="multi-analysis-header"><div><h1>{zh ? '多股主分析页' : 'Multi-stock analysis'}</h1><p>{selected.map(item => item.symbol).join(' · ')}</p></div><div className="multi-date-range"><span>{zh ? '数据区间' : 'Date range'}</span><strong>{dates[0] || '—'} → {dates.at(-1) || '—'}</strong></div><button onClick={() => setDetailsOpen(!detailsOpen)}>{detailsOpen ? (zh ? '隐藏详情' : 'Hide details') : (zh ? '显示详情' : 'Show details')}</button></header>
    {detailsOpen && <div className="multi-analysis-details"><span>{market === 'US' ? (zh ? '美股' : 'US stocks') : (zh ? 'A 股' : 'China A-shares')}</span><span>{selected.length} {zh ? '个对比标的' : 'symbols'}</span><span>{selected.reduce((sum, item) => sum + Number(item.rows || 0), 0).toLocaleString()} {zh ? '行行情' : 'price rows'}</span></div>}
    <nav className="multi-analysis-nav"><div>{[['basics', zh ? '基础信息' : 'Basic information'], ['strategy', zh ? '策略' : 'Strategy']].map(([value, label]) => <button key={value} aria-current={analysisTab === value} onClick={() => setAnalysisTab(value)}>{label}</button>)}</div><button onClick={() => setAnalysisStarted(false)}>{zh ? '股票池' : 'Stock pool'}</button></nav>
    {analysisTab === 'basics' ? <BasicSection {...{ zh, selected, dates, analyses, analysisError, factorScores, factorError, basicView, setBasicView }} /> : <StrategySection {...{ zh, selected, weights, setWeights, params, setParams, result, busy, error, run, trials, setTrials, optimize, optimization, download, labels, individual }} />}
  </main>
}

function BasicSection({ zh, selected, dates, analyses, analysisError, factorScores, factorError, basicView, setBasicView }) {
  const rows = selected.map(item => ({ ...item, analysis: analyses[item.symbol] }))
  const best = [...rows].filter(item => Number.isFinite(Number(item.analysis?.summary?.total_return))).sort((a, b) => Number(b.analysis.summary.total_return) - Number(a.analysis.summary.total_return))[0]
  return <section className="multi-basic-layout"><div className="multi-basic-summary"><div className="multi-kv-grid"><Metric label={zh ? '对比股票数' : 'Stocks'} value={selected.length} /><Metric label={zh ? '平均数据天数' : 'Average days'} value={Math.round(selected.reduce((sum, item) => sum + Number(item.rows || 0), 0) / selected.length)} /><Metric label={zh ? '区间表现最佳' : 'Top performer'} value={best?.symbol || 'N/A'} detail={best ? pct(best.analysis.summary.total_return) : ''} /><Metric label={zh ? '覆盖区间' : 'Coverage'} value={dates.length ? `${dates[0]} → ${dates.at(-1)}` : 'N/A'} /></div><div className="multi-stock-list"><h3>{zh ? '详细对比' : 'Detailed comparison'}</h3>{rows.map(item => <div key={item.dataset_id}><span><strong>{item.symbol}</strong><small>{item.source === 'upload' ? (zh ? '上传数据' : 'Uploaded') : (zh ? '市场数据' : 'Market data')} · {formatDate(item.date_range?.start) || '—'} — {formatDate(item.date_range?.end) || '—'}</small></span><em>{item.analysis?.summary?.latest_price == null ? `${Number(item.rows || 0).toLocaleString()} ${zh ? '天' : 'days'}` : `${Number(item.analysis.summary.latest_price).toFixed(2)} · ${pct(item.analysis.summary.total_return)}`}</em></div>)}</div></div><div className="multi-basic-chart"><header><h2>{basicTitle(basicView, zh)}</h2><p>{basicCopy(basicView, zh)}</p></header>{analysisError ? <Status state="error">{analysisError}</Status> : factorError && basicView === 'factor_score' ? <Status state="error">{factorError}</Status> : <BasicVisualization view={basicView} analyses={analyses} factorScores={factorScores} zh={zh} />}</div><aside className="multi-chart-switch"><span>{zh ? '图表切换' : 'Chart view'}</span>{BASIC_VIEWS.map(view => <button key={view} aria-pressed={basicView === view} onClick={() => setBasicView(view)}>{basicTitle(view, zh)}</button>)}</aside></section>
}

function BasicVisualization({ view, analyses, factorScores, zh }) {
  const entries = Object.entries(analyses)
  if (!entries.length) return <Status state="loading">{zh ? '正在准备 Python 分析结果' : 'Preparing Python analysis'}</Status>
  if (view === 'comparison' || view === 'relative_strength') {
    const normalized = Object.fromEntries(entries.map(([symbol, value]) => [symbol, normalizePrices(value.prices || [])])); const indexed = Object.fromEntries(Object.entries(normalized).map(([symbol, rows]) => [symbol, new Map(rows.map(row => [row.date, row.value]))])); const dates = [...new Set(Object.values(normalized).flatMap(rows => rows.map(row => row.date)))].sort()
    const benchmark = Object.fromEntries(dates.map(date => { const values = Object.values(indexed).map(rows => rows.get(date)).filter(Number.isFinite); return [date, values.length ? values.reduce((a, b) => a + b, 0) / values.length : null] }))
    const series = entries.map(([symbol]) => ({ name: symbol, data: view === 'comparison' ? normalized[symbol] : normalized[symbol].map(row => ({ date: row.date, value: benchmark[row.date] ? row.value / benchmark[row.date] : null })) }))
    return <LineChart series={series} name={basicTitle(view, zh)} height={430} />
  }
  if (view === 'risk_return') return <div className="multi-risk-plot">{entries.map(([symbol, value]) => <div key={symbol}><strong>{symbol}</strong><span>{zh ? '收益' : 'Return'} {pct(value.summary?.total_return)}</span><span>{zh ? '年化波动' : 'Annual volatility'} {pct(value.summary?.annualized_volatility)}</span></div>)}</div>
  if (view === 'factor_score') return !factorScores ? <Status state="loading">{zh ? '正在由 Python 计算因子评分' : 'Calculating factor scores in Python'}</Status> : <div className="multi-factor-list">{(factorScores.items || []).map(item => { const score = Number(item.factor_score); return <div key={item.symbol}><strong>{item.symbol}</strong>{Number.isFinite(score) ? <><span><i style={{ width: `${Math.min(100, Math.max(0, (score + 2) * 25))}%` }} /></span><em>{score.toFixed(2)}</em></> : <small>N/A</small>}</div> })}</div>
  const matrix = correlationMatrix(entries)
  return <div className="multi-correlation"><table><thead><tr><th></th>{entries.map(([symbol]) => <th key={symbol}>{symbol}</th>)}</tr></thead><tbody>{entries.map(([symbol], i) => <tr key={symbol}><th>{symbol}</th>{entries.map(([,], j) => <td key={j} style={{ backgroundColor: correlationColor(matrix[i][j]) }}>{Number.isFinite(matrix[i][j]) ? matrix[i][j].toFixed(2) : 'N/A'}</td>)}</tr>)}</tbody></table></div>
}

function StrategySection({ zh, selected, weights, setWeights, params, setParams, result, busy, error, run, trials, setTrials, optimize, optimization, download, labels, individual }) { return <section className="multi-strategy-layout"><div className="multi-strategy-controls"><p className="multi-kicker">{zh ? '控制面板' : 'Control'}</p><h2>{zh ? '多股策略控制台' : 'Multi-stock strategy console'}</h2><p className="caption">{zh ? '所有标的使用统一策略参数，组合权重在此集中配置。' : 'All symbols share one strategy configuration; portfolio weights are set here.'}</p><div className="multi-weights"><h3>{zh ? '组合权重配置' : 'Portfolio weights'}</h3>{selected.map(item => <Field key={item.dataset_id} label={item.symbol}><input disabled={busy} type="number" min="0" step="0.05" value={weights[item.dataset_id] ?? 1} onChange={e => setWeights({ ...weights, [item.dataset_id]: e.target.value })} /></Field>)}</div><details><summary>{zh ? '策略参数微调' : 'Strategy parameter tuning'}</summary><div className="multi-params">{Object.entries(params).map(([key, value]) => <Field key={key} label={key.replaceAll('_', ' ')}>{typeof value === 'boolean' ? <input type="checkbox" checked={value} onChange={e => setParams({ ...params, [key]: e.target.checked })} /> : <input type={typeof value === 'number' ? 'number' : 'text'} step="any" value={value} onChange={e => setParams({ ...params, [key]: typeof value === 'number' ? Number(e.target.value) : e.target.value })} />}</Field>)}</div></details><Button disabled={busy} onClick={run}>{busy ? (zh ? '正在生成' : 'Generating') : (zh ? '生成组合策略' : 'Generate portfolio strategy')}</Button><div className="multi-optimization"><h3>{zh ? '等权组合参数搜索' : 'Equal-weight parameter search'}</h3><p className="caption">{zh ? '搜索时暂用等权组合，完成后以最优参数重新计算。' : 'The search uses equal weights, then recalculates with the selected parameters.'}</p><Field label={zh ? '优化试验次数' : 'Optimization trials'}><input type="range" min="10" max="100" step="10" value={trials} onChange={e => setTrials(e.target.value)} /><strong>{trials}</strong></Field><Button variant="secondary" disabled={busy} onClick={optimize}>{zh ? '开始等权组合搜索' : 'Start equal-weight search'}</Button>{optimization && <Status>{zh ? '最优参数已应用并重新计算。' : 'Optimal parameters applied and recalculated.'}</Status>}</div></div><div className="multi-strategy-result"><div className="multi-result-heading"><div><p className="multi-kicker">{zh ? '结果' : 'Result'}</p><h2>{zh ? '组合策略结果' : 'Portfolio strategy result'}</h2></div>{result && <Button disabled={busy} variant="secondary" onClick={download}><Download size={16} />{zh ? '导出 HTML' : 'Export HTML'}</Button>}</div>{error && <Status state="error">{error}</Status>}{!result ? <Status>{zh ? '配置权重与参数后生成组合策略。' : 'Configure weights and parameters, then generate the portfolio.'}</Status> : <PortfolioResultContent {...{ result, zh, labels, individual }} />}</div></section> }

function PortfolioResultContent({ result, zh, labels, individual }) {
  const [view, setView] = useState('simulation'); const [period, setPeriod] = useState('M')
  const presentation = result.presentation
  return <><div className="multi-result-tabs" role="tablist"><button role="tab" aria-selected={view === 'simulation'} onClick={() => setView('simulation')}>{zh ? '组合模拟' : 'Portfolio simulation'}</button><button role="tab" aria-selected={view === 'heatmap'} onClick={() => setView('heatmap')}>{zh ? '周期收益热力图' : 'Periodic return heatmap'}</button></div>
    {view === 'simulation' ? <><LineChart series={[{ name: zh ? '组合策略' : 'Portfolio strategy', data: result.equity }, { name: zh ? '买入持有基准' : 'Buy-and-hold benchmark', data: result.benchmark }]} name={zh ? '组合净值' : 'Portfolio equity'} />{presentation?.drawdown?.length ? <div className="multi-drawdown"><h3>{zh ? '组合回撤' : 'Portfolio drawdown'}</h3><LineChart series={presentation.drawdown} valueKey="drawdown" name={zh ? '组合回撤' : 'Portfolio drawdown'} percent height={220} color="#b3483c" /></div> : <Status>{zh ? '此旧结果未保存回撤数据，请重新生成组合。' : 'This saved result predates drawdown data. Recalculate the portfolio.'}</Status>}</> : <><div className="multi-period-tabs">{[['M', zh ? '月度' : 'Monthly'], ['Q', zh ? '季度' : 'Quarterly'], ['YE', zh ? '年度' : 'Annual']].map(([key, label]) => <button key={key} aria-pressed={period === key} onClick={() => setPeriod(key)}>{label}</button>)}</div><PeriodicHeatmap data={presentation?.periodic_returns?.[period]} zh={zh} /></>}
    <div className="metric-grid featured">{Object.entries(result.metrics || {}).map(([key, value]) => <Metric key={key} label={labels[key] || key} value={value == null ? 'N/A' : key.includes('sharpe') ? Number(value).toFixed(2) : `${(Number(value) * 100).toFixed(2)}%`} />)}</div><details><summary>{zh ? '个股策略表现' : 'Individual stock performance'}</summary><DataTable rows={individual} columns={Object.keys(individual[0] || {}).map(key => ({ key, label: key.replaceAll('_', ' ') }))} /></details></>
}

function PeriodicHeatmap({ data, zh }) {
  if (!data) return <Status>{zh ? '此旧结果没有周期收益数据，请重新生成组合。' : 'This saved result has no periodic return data. Recalculate the portfolio.'}</Status>
  return <div className="multi-periodic-heatmap"><table><thead><tr><th></th>{data.x.map(label => <th key={label}>{label}</th>)}</tr></thead><tbody>{data.y.map((label, rowIndex) => <tr key={label}><th>{label === 'portfolio' ? (zh ? '组合策略' : 'Portfolio') : `${label} ${zh ? '策略' : 'strategy'}`}</th>{data.z[rowIndex].map((value, columnIndex) => <td key={data.x[columnIndex]} style={{ backgroundColor: periodicColor(value) }}>{value == null ? '' : `${Number(value).toFixed(1)}%`}</td>)}</tr>)}</tbody></table></div>
}

function normalizePrices(prices) {
  const first = prices.map(row => Number(row.close)).find(value => Number.isFinite(value) && value !== 0)
  if (!first) return []
  return prices.map(row => ({ date: row.date, value: Number.isFinite(Number(row.close)) ? Number(row.close) / first : null }))
}

function correlationMatrix(entries) {
  const returns = entries.map(([, value]) => {
    const map = new Map(); const rows = value.prices || []
    for (let i = 1; i < rows.length; i += 1) { const prev = Number(rows[i - 1].close); const next = Number(rows[i].close); if (Number.isFinite(prev) && prev !== 0 && Number.isFinite(next)) map.set(rows[i].date, next / prev - 1) }
    return map
  })
  return returns.map((left, i) => returns.map((right, j) => {
    if (i === j) return 1
    const pairs = [...left].filter(([date]) => right.has(date)).map(([date, value]) => [value, right.get(date)])
    if (pairs.length < 2) return NaN
    const ax = pairs.reduce((sum, pair) => sum + pair[0], 0) / pairs.length; const ay = pairs.reduce((sum, pair) => sum + pair[1], 0) / pairs.length
    const numerator = pairs.reduce((sum, pair) => sum + (pair[0] - ax) * (pair[1] - ay), 0); const dx = Math.sqrt(pairs.reduce((sum, pair) => sum + (pair[0] - ax) ** 2, 0)); const dy = Math.sqrt(pairs.reduce((sum, pair) => sum + (pair[1] - ay) ** 2, 0))
    return dx && dy ? numerator / (dx * dy) : NaN
  }))
}

function correlationColor(value) { if (!Number.isFinite(value)) return 'transparent'; const alpha = .08 + Math.abs(value) * .28; return value >= 0 ? `rgba(52,119,94,${alpha})` : `rgba(179,72,60,${alpha})` }
function periodicColor(value) { if (value == null || !Number.isFinite(Number(value))) return 'transparent'; const alpha = .08 + Math.min(Math.abs(Number(value)) / 20, 1) * .34; return Number(value) >= 0 ? `rgba(52,119,94,${alpha})` : `rgba(179,72,60,${alpha})` }
function pct(value) { return Number.isFinite(Number(value)) ? `${(Number(value) * 100).toFixed(2)}%` : 'N/A' }
function formatDate(value) { return value ? String(value).slice(0, 10) : '' }

function basicTitle(view, zh) { return ({ comparison: zh ? '价格对比' : 'Price comparison', relative_strength: zh ? '相对强度' : 'Relative strength', risk_return: zh ? '风险收益' : 'Risk and return', factor_score: zh ? '最新因子评分' : 'Latest factor scores', correlation: zh ? '相关性热力图' : 'Correlation heatmap' })[view] }
function basicCopy(view, zh) { return ({ comparison: zh ? '以统一起点观察标的走势差异。' : 'Compare price paths from a shared starting point.', relative_strength: zh ? '观察各标的相对等权基准的强弱。' : 'Compare each symbol with the equal-weight benchmark.', risk_return: zh ? '对照收益与波动水平。' : 'Compare returns with volatility.', factor_score: zh ? '比较 Python 因子流水线的最新评分。' : 'Compare the latest Python factor pipeline scores.', correlation: zh ? '观察标的收益率之间的相关关系。' : 'Inspect return correlations across symbols.' })[view] }
