import { useState } from 'react'
import { FigureChart, LineChart, MonthlyHeatmap } from '../../components/Charts'
import { DataTable, Field, Metric, Status } from '../../components/Primitives'
import { Segments } from './SinglePanels'

export function StrategyComparison({ entries, zh }) {
  const [focusIndex, setFocusIndex] = useState(0)
  const [detail, setDetail] = useState('signals')
  const [split, setSplit] = useState('test')
  const focus = entries[focusIndex] || entries[0]
  const artifact = focus.artifact
  const dates = new Set((artifact[split] || []).map(row => row.date))
  const percentKeys = new Set(['cumret', 'annret', 'maxdd', 'bench_cumret', 'bench_annret', 'bench_maxdd', 'excess_return', 'winrate', 'turnover'])
  const metrics = entries.map(entry => ({ strategy: entry.name, ...Object.fromEntries(Object.entries(entry.artifact.metrics || {}).map(([key, value]) => [key, typeof value === 'number' ? (percentKeys.has(key) ? `${(value * 100).toFixed(2)}%` : value.toFixed(3)) : value])) }))
  const focusRows = (artifact.signals || []).filter(row => dates.has(row.date))
  const signalTraces = [{ type: 'scatter', mode: 'lines', name: focus.name, x: focusRows.map(row => row.date), y: focusRows.map(row => row.close) }]
  for (const entry of entries) {
    const entryDates = new Set((entry.artifact[split] || []).map(row => row.date))
    for (const [key, label, symbol] of [['buy_signal', zh ? '买入' : 'Buy', 'triangle-up'], ['sell_signal', zh ? '卖出' : 'Sell', 'triangle-down']]) {
      const rows = (entry.artifact.signals || []).filter(row => entryDates.has(row.date) && (row[key] === true || row[key] === 1))
      signalTraces.push({ type: 'scatter', mode: 'markers', name: `${entry.name} · ${label}`, x: rows.map(row => row.date), y: rows.map(row => row.close), marker: { symbol, size: 9 } })
    }
  }
  const columns = [...new Set(metrics.flatMap(row => Object.keys(row)))].filter(key => key !== 'label').map(key => ({ key, label: key === 'strategy' ? (zh ? '策略' : 'Strategy') : key }))
  const quality = entries.filter(entry => entry.artifact.ml_quality).map(entry => ({ strategy: entry.name, ...Object.fromEntries(Object.entries(entry.artifact.ml_quality).map(([key, value]) => [key, typeof value === 'object' ? JSON.stringify(value) : value])) }))
  return <div className="result-board">
    <h3>{zh ? '策略对比' : 'Strategy comparison'}</h3>
    <div className="metric-grid"><Metric label={zh ? '所选策略' : 'Selected strategies'} value={entries.length}/><Metric label={zh ? '焦点策略' : 'Focus strategy'} value={focus.name}/></div>
    <Field label={zh ? '焦点策略' : 'Focus strategy'}><select value={focusIndex} onChange={event => setFocusIndex(Number(event.target.value))}>{entries.map((entry, index) => <option value={index} key={entry.id}>{entry.name}</option>)}</select></Field>
    <h3>{zh ? '多策略净值与回撤' : 'Strategy equity and drawdown'}</h3>
    <LineChart series={entries} name={zh ? '策略净值比较' : 'Strategy equity comparison'}/>
    <LineChart series={entries.map(entry => ({ name: entry.name, data: entry.artifact.diagnostics?.test?.drawdown || [], valueKey: 'drawdown' }))} name={zh ? '策略回撤比较' : 'Strategy drawdown comparison'} percent height={260}/>
    <h3>{zh ? '焦点策略月度收益' : 'Focus strategy monthly returns'}</h3>
    <MonthlyHeatmap rows={artifact.diagnostics?.test?.monthly_returns || []}/>
    <h3>{zh ? '策略指标对比' : 'Strategy metrics'}</h3><DataTable rows={metrics} columns={columns}/>
    <Segments label={zh ? '对比详情' : 'Comparison details'} value={detail} onChange={setDetail} options={[["signals", zh ? '买卖点对比' : 'Trade signals'], ['ml', zh ? 'ML 质量' : 'ML quality']]}/>
    {detail === 'signals' ? <><Segments label={zh ? '信号区间' : 'Signal split'} value={split} onChange={setSplit} options={[["train", zh ? '训练集' : 'Train'], ['test', zh ? '测试集' : 'Test']]}/><FigureChart figure={{ data: signalTraces, layout: { height: 420 } }} name={zh ? '买卖点对比' : 'Trade signal comparison'}/></> : quality.length ? <DataTable rows={quality} columns={[...new Set(quality.flatMap(row => Object.keys(row)))].map(key => ({ key, label: key }))}/> : <Status>{zh ? '所选策略没有 ML 质量指标。' : 'No ML quality metrics for the selected strategies.'}</Status>}
  </div>
}
