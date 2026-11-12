import { useRef } from 'react'
import { RefreshCw, Upload } from 'lucide-react'
import { api } from '../../api/client'
import { useAsync } from '../../hooks/useAsync'
import { Button, Field, Metric, Status } from '../../components/Primitives'
import { CandleChart, IndicatorChart } from '../../components/Charts'
import { StockSearch } from '../../components/StockSearch'
import '../multi-stock.css'

export function Segments({label,value,onChange,options,disabled=false}) {
  return <div className="single-segments" role="group" aria-label={label}>{options.map(([id,title])=><button key={id} disabled={disabled} aria-pressed={value===id} onClick={()=>onChange(id)}>{title}</button>)}</div>
}

export function SingleEntry({zh,market,setMarket,query,setQuery,selected,setSelected,adjust,setAdjust,startDate,setStartDate,endDate,setEndDate,loadSelected,upload,busy,error,onResume}) {
  const file=useRef(null)
  const context=useAsync(()=>api.marketContext(market),[market],true)
  const selectedValue=selected || (query.trim()?{symbol:market==='US'?query.trim().toUpperCase():query.trim().padStart(6,'0')}:null)
  const changeMarket=value=>{if(busy)return;setMarket(value);setSelected(null);setQuery('')}
  return <main id="main" className="page multi-page multi-entry single-entry">
    <header className="multi-intro"><p>{zh?'单股分析':'Single-stock analysis'}</p><h1>{zh?'单股策略分析':'Single-stock strategy analysis'}</h1></header>
    <div className="multi-entry-grid"><section className="multi-action-panel"><h2>{zh?'选择股票':'Select a stock'}</h2>
      <div className="multi-market-toggle" role="radiogroup">{['US','CN_A'].map(value=><button key={value} disabled={busy} role="radio" aria-checked={market===value} onClick={()=>changeMarket(value)}>{value==='US'?(zh?'美股':'US stocks'):(zh?'A 股':'China A-shares')}</button>)}</div>
      <div className="multi-block"><h3>{zh?'数据设置':'Data settings'}</h3><div className="multi-entry-fields"><Field label={zh?'复权方式':'Adjustment'}><select value={adjust} onChange={e=>setAdjust(e.target.value)}><option value="qfq">{zh?'前复权':'Forward adjusted'}</option><option value="hfq">{zh?'后复权':'Backward adjusted'}</option><option value="none">{zh?'不复权':'Unadjusted'}</option></select></Field><Field label={zh?'起始日期':'Start date'}><input type="date" value={startDate} onChange={e=>setStartDate(e.target.value)}/></Field><Field label={zh?'结束日期':'End date'}><input type="date" value={endDate} onChange={e=>setEndDate(e.target.value)}/></Field></div></div>
      <div className="multi-block"><h3>{zh?'搜索股票':'Search stocks'}</h3><StockSearch zh={zh} market={market} query={query} onQueryChange={value=>{setQuery(value);setSelected(null)}} onSelect={item=>{setSelected(item);setQuery(item.symbol)}} disabled={busy}/><Button className="single-entry-start" disabled={busy||!selectedValue} onClick={()=>loadSelected(selectedValue)}>{busy?(zh?'正在加载':'Loading'):(zh?'开始单股分析':'Start single-stock analysis')}</Button></div>
      <div className="multi-block"><div className="multi-block-heading"><h3>{zh?'上传本地单股 CSV':'Upload a local single-stock CSV'}</h3><span title="date, open, high, low, close, volume">CSV ?</span></div><details><summary>{zh?'查看标准化 CSV 数据要求':'View CSV requirements'}</summary><p>{zh?'必需列：date、open、high、low、close；建议包含 volume。日期按交易日排序。':'Required: date, open, high, low, close. Volume is recommended. Sort by trading date.'}</p><code>date,open,high,low,close,volume</code></details><input ref={file} type="file" accept=".csv,text/csv" hidden onChange={e=>upload(e.target.files?.[0])}/><Button disabled={busy} variant="secondary" onClick={()=>file.current?.click()}><Upload size={16}/>{zh?'选择 CSV 文件':'Choose CSV file'}</Button></div>
      {error&&<Status state="error">{error}</Status>}{onResume&&<Button className="single-entry-resume" variant="secondary" onClick={onResume}>{zh?'返回当前分析':'Return to current analysis'}</Button>}
    </section><aside className="multi-showcase"><p className="multi-kicker">{zh?'市场展示板':'Market showcase'}</p><h2>{zh?'市场快照与推荐入口':'Market snapshot and recommendations'}</h2><div className="multi-showcase-heading"><h3>{zh?'市场快照':'Market snapshot'}</h3><button disabled={context.status==='loading'} onClick={()=>context.run()}><RefreshCw size={14}/>{zh?'刷新市场快照':'Refresh'}</button></div>
      {context.status==='error'&&<Status state="error" onRetry={context.run}>{context.error?.message}</Status>}<div className="multi-snapshot-grid">{context.data?.indices?.length?context.data.indices.map((item,index)=><div key={item.symbol||item.label||index}><span>{item.label||item.name||item.symbol||'—'}</span><strong>{item.close_text||item.close||item.value||'N/A'}</strong><small className={String(item.pct_text||'').startsWith('-')?'negative':'positive'}>{item.pct_text||item.change||''}</small></div>):<Status state={context.status==='loading'?'loading':undefined}>{context.status==='loading'?(zh?'加载市场快照':'Loading market snapshot'):(zh?'市场快照暂不可用':'Market snapshot unavailable')}</Status>}</div>
      <p className="caption">{zh?`推荐来源：${context.data?.recommendation_source||'市场上下文观察池'}`:`Source: ${context.data?.recommendation_source||'market context watchlist'}`}</p><div className="multi-recommend-sheet" role="region" tabIndex={0} aria-label={zh ? '推荐股票，可滚动' : 'Recommended stocks, scrollable'}><h3>{zh?'推荐股票':'Recommended stocks'}</h3>{(context.data?.recommendations||[]).slice(0,8).map(item=><div className="multi-picker-row" key={item.symbol}><span><strong>{item.symbol}{item.name?` · ${item.name}`:''}</strong><small>{item.heat_text?`${zh?'热度':'Heat'} ${item.heat_text} · `:''}{item.pct_text||item.change_text||''}</small></span><button disabled={busy} onClick={()=>loadSelected(item)}>{zh?'分析':'Analyze'}</button></div>)}{context.status==='success'&&!context.data?.recommendations?.length&&<Status>{zh?'暂无推荐股票':'No recommendations available'}</Status>}</div>
    </aside></div>
  </main>
}

const number=value=>typeof value==='number'&&Number.isFinite(value)?value.toLocaleString(undefined,{maximumFractionDigits:2}):'N/A'
const pct=value=>typeof value==='number'&&Number.isFinite(value)?(value*100).toFixed(2)+'%':'N/A'
export function SingleBasics({zh,resource,period,setPeriod,scope,setScope,indicator,setIndicator}) {
  const s=resource.data?.summary; const latest=s?.latest||{}; const snap=s?.snapshot||{}
  const technical=[[zh?'RSI 状态':'RSI state',number(snap.rsi),snap.rsi>=snap.rsi_upper?(zh?'偏热':'Hot'):snap.rsi<=snap.rsi_lower?(zh?'偏冷':'Cold'):snap.rsi>=50?(zh?'中性偏强':'Neutral bullish'):(zh?'中性偏弱':'Neutral weak')],[zh?'MACD 柱值':'MACD histogram',number(snap.histogram),snap.histogram>0?(zh?'多头动能':'Bullish momentum'):(zh?'空头动能':'Bearish momentum')],[zh?'相对成交量':'Relative volume',snap.relative_volume==null?'N/A':number(snap.relative_volume)+'x',snap.relative_volume>=1.15?(zh?'放量':'Elevated'):snap.relative_volume<=.85?(zh?'缩量':'Lower'):(zh?'量能平稳':'Stable')],[zh?'区间位置':'Range position',pct(snap.range_position),snap.range_position>=.67?(zh?'接近高位':'Near high'):snap.range_position>=.33?(zh?'区间中部':'Middle'):(zh?'接近低位':'Near low')],[zh?'60 日波动率':'60-day volatility',pct(snap.volatility_60d),snap.volatility_60d>=.4?(zh?'波动较高':'High'):snap.volatility_60d>=.2?(zh?'波动适中':'Moderate'):(zh?'低波动':'Low')],[zh?'EMA 间距':'EMA spread',pct(snap.ema_spread),snap.ema_spread>0?(zh?'快线上方':'Fast above'):(zh?'快线下方':'Fast below')]]
  const rows=(resource.data?.candles||[]).filter(row=>scope!=='train'||row.date<=s?.split_date)
  const metrics=[
    [zh?'当前价格':'Current price',number(s?.latest_price)], [zh?'最新涨跌':'Latest change',pct(s?.change_pct)],
    [zh?'开盘 / 最高':'Open / high',`${number(latest.open)} / ${number(latest.high)}`], [zh?'最低 / 成交量':'Low / volume',`${number(latest.low)} / ${number(latest.volume)}`],
    [zh?'区间收益':'Period return',pct(s?.total_return)],[zh?'20 日均量':'20-day average volume',number(s?.volume_20d)],
    [zh?'训练集截止':'Training cutoff',s?.split_date?.slice(0,10)||'N/A'], [zh?'数据行数':'Data rows',s?.rows||'N/A']]
  return <section className="single-basics"><h2>{zh?'单股基础信息区':'Single-stock basic information'}</h2>
    {resource.status==='loading'&&<Status state="loading">{zh?'正在加载基础信息':'Loading basic information'}</Status>}{resource.status==='error'&&<Status state="error" onRetry={resource.run}>{resource.error?.message}</Status>}
    <div className="single-basics-grid"><aside><div className="single-kv">{metrics.map(([label,value])=><Metric key={label} label={label} value={value}/>)}</div><h3>{zh?'技术快照':'Technical snapshot'}</h3><div className="single-kv">{technical.map(([label,value,detail])=><Metric key={label} label={label} value={value} detail={value==='N/A'?undefined:detail}/>)}</div><p className="caption">{zh?'缺失字段显示 N/A，不影响其他基础信息。':'Missing fields display N/A without hiding other information.'}</p></aside>
    <div className="single-market-charts"><div className="single-chart-controls"><Field label={zh?'股票周期':'Period'}><Segments label="Period" value={period} onChange={setPeriod} options={[["D",zh?'日 K':'Daily'],['W',zh?'周 K':'Weekly'],['M',zh?'月 K':'Monthly']]}/></Field><Field label={zh?'数据集时间':'Data scope'}><Segments label="Data scope" value={scope} onChange={setScope} options={[["dataset",zh?'全部':'All'],['train',zh?'训练集':'Train']]}/></Field><Field label={zh?'指标副图':'Indicator'}><Segments label="Indicator" value={indicator} onChange={setIndicator} options={[["MACD",'MACD'],['RSI','RSI'],['VOL',zh?'成交量':'Volume']]}/></Field></div>
    <CandleChart key={`${period}-${scope}-${rows[0]?.date}-${rows.at(-1)?.date}-${rows.length}`} rows={rows} visiblePoints={32} name={zh?'价格 K 线':'Price candlesticks'}/><IndicatorChart rows={rows} indicator={indicator}/>

    </div></div>
  </section>
}
