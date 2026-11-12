import { lazy, Suspense, useState } from 'react'
import { useApp } from '../state/AppContext'
import { finite, monthlyMatrix, toSeries } from './chart-data'

const Plot = lazy(() => Promise.all([
  import('react-plotly.js/factory'), import('plotly.js-dist-min'),
]).then(([factory, plotly]) => ({ default: factory.default(plotly.default) })))

function Chart({ data, name, height = 360, layout = {}, onRelayout }) {
  const { theme, language } = useApp()
  const dark = theme === 'dark'
  const text = dark ? '#f3f1ea' : '#202124'
  const grid = dark ? '#34353a' : '#deded9'
  return <div className="chart-wrap" role="figure" aria-label={name}>
    <Suspense fallback={<p role="status">{language === 'zh' ? '正在加载图表…' : 'Loading chart…'}</p>}>
      <Plot data={data} onRelayout={onRelayout} layout={{ height, autosize: true, margin: { l: 52, r: 20, t: 25, b: 48 },
        paper_bgcolor: 'transparent', plot_bgcolor: 'transparent',
        font: { family: 'Manrope, sans-serif', color: text },
        xaxis: { gridcolor: grid, zeroline: false }, yaxis: { gridcolor: grid, zeroline: false },
        legend: { orientation: 'h', x: 0, y: 1.15 }, hovermode: 'x unified', ...layout }}
        config={{ responsive: true, displaylogo: false, showLink: false,
          modeBarButtonsToRemove: ['lasso2d', 'select2d', 'sendDataToCloud', 'share'] }}
        useResizeHandler style={{ width: '100%' }} />
    </Suspense>
  </div>
}

export function LineChart({ series, name = 'Value', height = 360, color = '#2457ff', percent = false, valueKey }) {
  const { theme } = useApp()
  const palette = ['#2457ff', theme === 'dark' ? '#dadbdc' : '#55585e', '#bb513d', '#62805d']
  const traces = Array.isArray(series) && series[0]?.data ? series : [{ data: series, name, color, valueKey }]
  const data = traces.map((item, i) => ({ ...toSeries(item.data, item.valueKey), type: 'scatter', mode: 'lines',
    name: item.name, connectgaps: false, line: { color: item.color || palette[i % palette.length], width: 2 },
    hovertemplate: percent ? '%{y:.2%}<extra>%{fullData.name}</extra>' : '%{y:.3f}<extra>%{fullData.name}</extra>' }))
  return <Chart data={data} name={name} height={height} layout={percent ? { yaxis: { tickformat: '.1%', zeroline: false, gridcolor: theme === 'dark' ? '#34353a' : '#deded9' } } : {}} />
}

export function FigureChart({ figure, name = 'Chart' }) {
  if (!figure?.data?.length) return null
  const { paper_bgcolor, plot_bgcolor, font, template, ...layout } = figure.layout || {}
  return <Chart data={figure.data} name={name} height={layout.height || 360} layout={layout}/>
}

export function DrawdownChart({ equity }) {
  const { language } = useApp()
  const values = toSeries(equity)
  let peak = -Infinity
  const y = values.y.map(value => {
    if (value == null) return null
    peak = Math.max(peak, value)
    return peak > 0 ? value / peak - 1 : null
  })
  return <LineChart series={values.x.map((date, i) => ({ date, value: y[i] }))} name={language === 'zh' ? '回撤' : 'Drawdown'} color="#bb513d" percent height={260} />
}

export function CandleChart({ rows = [], name, visiblePoints }) {
  const { language } = useApp()
  const label = name || (language === 'zh' ? '价格与交易信号' : 'Price and trade signals')
  const [visibleRange, setVisibleRange] = useState(null)
  const viewportRows = visibleRange === 'all' ? rows : Array.isArray(visibleRange) ? rows.filter(row => { const date = Date.parse(row.date); return date >= Date.parse(visibleRange[0]) && date <= Date.parse(visibleRange[1]) }) : visiblePoints ? rows.slice(-visiblePoints) : []
  const handleRelayout = event => {
    if (!visiblePoints) return
    if (event['xaxis.autorange']) setVisibleRange('all')
    else { const range = event['xaxis.range'] || [event['xaxis.range[0]'], event['xaxis.range[1]']]; if (range[0] != null && range[1] != null) setVisibleRange(range) }
  }
  const lows = viewportRows.map(row => finite(row.low)).filter(value => value != null)
  const highs = viewportRows.map(row => finite(row.high)).filter(value => value != null)
  const low = Math.min(...lows); const high = Math.max(...highs)
  const padding = Math.max((high - low) * .08, Math.abs(high) * .005)
  const priceAxis = lows.length && highs.length ? { range: [low - padding, high + padding] } : {}
  const data = [{ type: 'candlestick', x: rows.map(row => row.date), open: rows.map(row => finite(row.open)),
    high: rows.map(row => finite(row.high)), low: rows.map(row => finite(row.low)), close: rows.map(row => finite(row.close)),
    name: label, increasing: { line: { color: '#34775e' } }, decreasing: { line: { color: '#b3483c' } } }]
  for (const [key, title, color, symbol] of [['buy_signal', language === 'zh' ? '买入信号' : 'Buy signal', '#2457ff', 'triangle-up'], ['sell_signal', language === 'zh' ? '卖出信号' : 'Sell signal', '#b3483c', 'triangle-down']]) {
    const signals = rows.filter(row => row[key] === true || row[key] === 1)
    if (signals.length) data.push({ type: 'scatter', mode: 'markers', name: title, x: signals.map(row => row.date), y: signals.map(row => row.close), marker: { color, symbol, size: 9 } })
  }
  return <Chart data={data} name={label} height={420} onRelayout={handleRelayout} layout={{ xaxis: { rangeslider: { visible: true, thickness: 0.1 }, ...(visibleRange==='all'?{autorange:true}:Array.isArray(visibleRange)?{range:visibleRange}:visiblePoints&&rows.length>visiblePoints?{range:[rows[rows.length-visiblePoints].date,rows.at(-1).date]}:{}) }, yaxis: priceAxis, hovermode: 'closest' }} />
}

export function IndicatorChart({ rows = [], indicator = 'MACD', visiblePoints = 32 }) {
  const { language } = useApp()
  const x = rows.map(row=>row.date)
  const line = (key,name,color) => ({ x,y:rows.map(row=>finite(row[key])),name,type:'scatter',mode:'lines',line:{color,width:1.5} })
  const data=indicator==='MACD'?[line('macd','MACD','#2457ff'),line('signal',language==='zh'?'信号线':'Signal','#a88046'),{x,y:rows.map(row=>finite(row.histogram)),type:'bar',name:language==='zh'?'MACD 柱值':'Histogram',marker:{color:rows.map(row=>row.histogram>=0?'#34775e':'#b3483c')}}]:indicator==='RSI'?[line('rsi','RSI','#2457ff')]:[{x,y:rows.map(row=>finite(row.volume)),type:'bar',name:language==='zh'?'成交量':'Volume',marker:{color:'#62805d'}}]
  return <Chart data={data} name={indicator} height={230} layout={{xaxis:rows.length>visiblePoints?{range:[rows[rows.length-visiblePoints].date,rows.at(-1).date]}:{}}}/>
}

export function MonthlyHeatmap({ rows = [] }) {
  const { language } = useApp()
  const { years, z } = monthlyMatrix(rows)
  if (!years.length) return <p>{language === 'zh' ? '暂无周期收益数据' : 'No periodic returns available'}</p>
  return <Chart name={language === 'zh' ? '月度收益' : 'Monthly returns'} height={Math.max(220, years.length * 32 + 90)}
    data={[{ type: 'heatmap', x: Array.from({ length: 12 }, (_, i) => String(i + 1)), y: years, z,
      colorscale: [[0, '#b3483c'], [0.5, '#fafaf8'], [1, '#34775e']], zmid: 0,
      hoverongaps: false, hovertemplate: '%{y}-%{x}: %{z:.2%}<extra></extra>',
      texttemplate: '%{z:.1%}', colorbar: { tickformat: '.0%' } }]}
    layout={{ hovermode: 'closest', yaxis: { type: 'category', autorange: 'reversed' }, xaxis: { type: 'category', title: { text: language === 'zh' ? '月份' : 'Month' } } }} />
}
