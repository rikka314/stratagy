import { FigureChart } from '../../components/Charts'
import { DataTable, Metric, Status } from '../../components/Primitives'

const PERCENT_METRICS = new Set(['cumret', 'annret', 'maxdd', 'winrate', 'turnover', 'excess_return'])

function number(value) {
  if (value == null || value === '') return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function metricValue(key, value, zh) {
  const parsed = number(value)
  if (parsed == null) return value ?? 'N/A'
  if (PERCENT_METRICS.has(key)) return parsed.toLocaleString(zh ? 'zh-CN' : 'en-US', { style: 'percent', maximumFractionDigits: 2 })
  return parsed.toLocaleString(zh ? 'zh-CN' : 'en-US', { maximumFractionDigits: 3 })
}

function regimeLabel(value) {
  return ({ trend_follow: 'Trend Follow', range_selective: 'Range Selective', risk_off: 'Risk Off' })[value] || value || 'N/A'
}

function actionText(latest, zh) {
  const target = number(latest?.target_position) ?? 0
  const regime = regimeLabel(latest?.execution_regime)
  if (latest?.buy_signal) return zh ? `最新信号偏多，目标仓位 ${target.toFixed(1)}，执行分支 ${regime}。` : `Latest signal is bullish; target position ${target.toFixed(1)}, execution branch ${regime}.`
  if (latest?.sell_signal) return zh ? `最新信号偏空，目标仓位 ${target.toFixed(1)}，执行分支 ${regime}。` : `Latest signal is bearish; target position ${target.toFixed(1)}, execution branch ${regime}.`
  if (target >= .8) return zh ? `当前维持高仓位，目标仓位 ${target.toFixed(1)}，执行分支 ${regime}。` : `Maintaining a high position at ${target.toFixed(1)}; execution branch ${regime}.`
  if (target >= .2) return zh ? `当前处于观察仓位，目标仓位 ${target.toFixed(1)}，执行分支 ${regime}。` : `Holding an observation position at ${target.toFixed(1)}; execution branch ${regime}.`
  return zh ? `当前更接近观望状态，执行分支 ${regime}。` : `The strategy is currently close to neutral; execution branch ${regime}.`
}

function scoreColumns(rows) {
  if (rows.some((row) => Object.hasOwn(row, 'factor_score') && Object.hasOwn(row, 'factor_percentile'))) return ['factor_score', 'factor_percentile', 'Factor']
  if (rows.some((row) => Object.hasOwn(row, 'regime_score') && Object.hasOwn(row, 'regime_score_percentile'))) return ['regime_score', 'regime_score_percentile', 'Regime']
  return [null, null, 'Score']
}

export function ResultSummary({ artifact, zh }) {
  const signals = Array.isArray(artifact.signals) ? artifact.signals : []
  const latest = signals.at(-1) || {}
  const [scoreKey, percentileKey, scoreName] = scoreColumns(signals)
  const score = scoreKey ? number(latest[scoreKey]) : null
  const percentile = percentileKey ? number(latest[percentileKey]) : null
  const finalStage = Array.isArray(artifact.lineage) ? artifact.lineage.at(-1) : null
  const regime = finalStage?.metadata?.regime_summary
  const latestRegime = regimeLabel(latest.execution_regime || regime?.latest_execution_regime)
  const target = number(latest.target_position) ?? 0
  const summary = [
    [zh ? '当前策略' : 'Current strategy', artifact.display_label || 'N/A', zh ? '当前生成产物' : 'Generated artifact'],
    [zh ? '最新建议' : 'Latest suggestion', actionText(latest, zh), zh ? '来自最后一个信号日' : 'From the latest signal row'],
    [zh ? '目标仓位' : 'Target position', target.toFixed(1), zh ? '最新 target_position' : 'Latest target_position'],
    [`${scoreName} ${zh ? '评分 / 分位' : 'score / percentile'}`, score == null ? 'N/A' : score.toFixed(2), percentile == null ? 'N/A' : `${(percentile * 100).toFixed(1)}%`],
  ]
  return <>
    <section className="result-summary"><h3>{zh ? '当前策略摘要' : 'Current strategy summary'}</h3><p className="caption">{zh ? `${artifact.display_label || '当前策略'}：${actionText(latest, zh)}` : `${artifact.display_label || 'Current strategy'}: ${actionText(latest, zh)}`}</p><div className="metric-grid featured">{summary.map(([label, value, detail]) => <Metric key={label} label={label} value={value} detail={detail} />)}</div></section>
    <section className="result-lineage"><h3>{zh ? '当前工作流链路' : 'Current workflow lineage'}</h3><p className="caption">{(artifact.lineage || []).map((stage) => stage.display_label || stage.stage_key).join(' → ') || 'N/A'}</p><div className="metric-grid featured">{(artifact.lineage || []).map((stage, index) => <div className="metric" key={`${stage.stage_key}-${index}`}><span>{stage.display_label || stage.stage_key}</span><strong>{metricValue('cumret', stage.metrics?.cumret, zh)}</strong><small>{zh ? '累计收益' : 'Cumulative return'} · {zh ? '最大回撤' : 'Max drawdown'} {metricValue('maxdd', stage.metrics?.maxdd, zh)} · Sharpe {metricValue('sharpe', stage.metrics?.sharpe, zh)}{stage.metadata?.search_method ? ` · ${zh ? '参数搜索' : 'Search'} ${stage.metadata.search_method}` : ''}</small></div>)}</div></section>
    {regime && <section className="result-regime"><h3>Regime Diagnostics</h3><div className="metric-grid featured"><Metric label={zh ? '市场代理' : 'Market proxy'} value={regime.market_proxy_symbol || 'SPY'} detail={regime.market_proxy_mode || 'enabled'} /><Metric label={zh ? '代理模式' : 'Proxy mode'} value={regime.market_proxy_mode || 'enabled'} detail="enabled / disabled / fallback" /><Metric label={zh ? '最新 Regime' : 'Latest regime'} value={latestRegime} /></div>{Array.isArray(regime.regime_table) && regime.regime_table.length > 0 && <DataTable rows={regime.regime_table.map((row) => ({ ...row, regime: regimeLabel(row.regime) }))} columns={[{ key: 'regime', label: 'Regime' }, { key: 'day_count', label: zh ? '天数' : 'Days' }, { key: 'day_ratio', label: zh ? '时间占比' : 'Time ratio' }, { key: 'return_contribution', label: zh ? '收益贡献' : 'Return contribution' }, { key: 'exposure_ratio', label: zh ? '仓位占比' : 'Exposure ratio' }]} />}{signals.some((row) => row.execution_regime) && <FigureChart name={zh ? '最近 30 个交易日 Regime' : 'Regime over the last 30 trading days'} figure={{ data: [{ type: 'bar', x: signals.slice(-30).map((row) => row.date), y: signals.slice(-30).map(() => 1), customdata: signals.slice(-30).map((row) => regimeLabel(row.execution_regime)), hovertemplate: '%{x}<br>%{customdata}<extra></extra>', marker: { color: signals.slice(-30).map((row) => ({ trend_follow: '#1d6f6d', range_selective: '#c27a2c', risk_off: '#a84a3c' })[row.execution_regime] || '#7d5a9e') } }], layout: { height: 220, bargap: .12, yaxis: { visible: false, range: [0, 1.2] }, showlegend: false } }} />}{regime.market_proxy_warning && <Status state="error">{regime.market_proxy_warning}</Status>}</section>}
  </>
}

export function FactorScorePanel({ artifact, split, zh }) {
  const signals = Array.isArray(artifact.signals) ? artifact.signals : []
  const splitDates = new Set((artifact[split] || []).map((row) => row.date))
  const rows = signals.filter((row) => splitDates.has(row.date))
  const [scoreKey, percentileKey, scoreName] = scoreColumns(rows)
  const points = scoreKey ? rows.filter((row) => number(row[scoreKey]) != null || number(row[percentileKey]) != null) : []
  return <details><summary>{zh ? '可选：评分与分位走势' : 'Optional: score and percentile history'}</summary>{points.length ? <><p className="caption">{zh ? `当前展示${split === 'test' ? '测试集' : '训练集'} ${scoreName} 评分和分位数。` : `Showing ${scoreName} score and percentile for the ${split} split.`}</p><FigureChart name={`${scoreName} score`} figure={{ data: [{ type: 'scatter', mode: 'lines', name: zh ? '评分' : 'Score', x: points.map((row) => row.date), y: points.map((row) => number(row[scoreKey])) }, { type: 'scatter', mode: 'lines', name: zh ? '分位' : 'Percentile', x: points.map((row) => row.date), y: points.map((row) => number(row[percentileKey]) == null ? null : number(row[percentileKey]) * 100), yaxis: 'y2' }], layout: { height: 360, yaxis: { title: { text: zh ? '评分' : 'Score' } }, yaxis2: { title: { text: zh ? '分位（%）' : 'Percentile (%)' }, overlaying: 'y', side: 'right' } } }} /></> : <Status>{zh ? `当前没有可展示的${split === 'test' ? '测试集' : '训练集'}评分。` : `No score history is available for the ${split} split.`}</Status>}</details>
}
