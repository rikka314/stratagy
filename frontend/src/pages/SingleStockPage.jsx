import { useEffect, useRef, useState } from 'react'
import { Download } from 'lucide-react'
import { api } from '../api/client'
import { CandleChart, DrawdownChart, LineChart, MonthlyHeatmap } from '../components/Charts'
import { Button, DataTable, Field, Metric, Status } from '../components/Primitives'
import { useAsync } from '../hooks/useAsync'
import { useApp } from '../state/AppContext'

import { SingleEntry, SingleBasics, Segments } from './single/SinglePanels'
import { FactorScorePanel, ResultSummary } from './single/ResultSummary'
import './single/single.css'
import { StrategyComparison } from './single/StrategyComparison'

const families = ['baseline', 'search', 'regime', 'composite']
const baselineKinds = ['naive', 'mean', 'drift']
const compositePolicies = ['composite_only', 'composite_plus_trend', 'composite_plus_reversion', 'composite_plus_relative_strength', 'composite_plus_macro_cap', 'composite_plus_all_advisories']


export function SingleStockPage() {
  const { language, addDataset, addSingleJob, workspace, setWorkspace } = useApp(); const zh = language === 'zh'
  const [market, setMarket] = useState(workspace.singleDraft?.market||'US'); const [query, setQuery] = useState(''); const [selected, setSelected] = useState(null)
  const [adjust,setAdjust]=useState('qfq'); const [startDate,setStartDate]=useState(''); const [endDate,setEndDate]=useState(''); const [forceRefresh,setForceRefresh]=useState(false)
  const [dataset, setDataset] = useState(workspace.datasets.find(item=>item.dataset_id===workspace.singleDatasetId) || null); const [family, setFamily] = useState(workspace.singleDraft?.family||'')
  const [view,setView]=useState(workspace.singleDatasetId?'analysis':'entry'); const [section,setSection]=useState('basics'); const [showDetails,setShowDetails]=useState(false); const [period,setPeriod]=useState('D'); const [scope,setScope]=useState('dataset'); const [indicator,setIndicator]=useState('MACD'); const [resultView,setResultView]=useState('workspace')
  const [baselineKind, setBaselineKind] = useState('naive'); const [compositePolicy, setCompositePolicy] = useState('composite_only')
  const [regimeKind, setRegimeKind] = useState('adaptive_router_v1'); const [params, setParams] = useState(workspace.singleDraft?.params||{})
  const [searchBase, setSearchBase] = useState('sm'); const [searchMethod, setSearchMethod] = useState('bayesian')
  const [useMl,setUseMl]=useState(false); const [useNews,setUseNews]=useState(false); const [riskBudget,setRiskBudget]=useState(1); const [positionMethod,setPositionMethod]=useState('linear_clip')
  const [useParameterSearch,setUseParameterSearch]=useState(false); const [searchTrials,setSearchTrials]=useState(60); const [mlModel,setMlModel]=useState('logistic'); const [mlHorizon,setMlHorizon]=useState(10); const [newsWeight,setNewsWeight]=useState(.4); const [newsLookback,setNewsLookback]=useState(20)
  const [compareIds,setCompareIds]=useState([]); const [compareSeries,setCompareSeries]=useState([])
  const [trainRatio, setTrainRatio] = useState(workspace.singleDraft?.trainRatio||.7); const [job, setJob] = useState(() => workspace.singleJobs.find(item=>item.dataset_id===workspace.singleDatasetId) || null); const [result, setResult] = useState(null)
  const [formError, setFormError] = useState(''); const [dataBusy,setDataBusy]=useState(false); const actionGeneration=useRef(0)
  const metadata = useAsync(() => api.metadata(), [], true)
  const basics = useAsync(() => dataset?.dataset_id ? api.datasetAnalysis(dataset.dataset_id,{period,train_ratio:trainRatio,params}) : Promise.resolve(null),[dataset?.dataset_id,period,trainRatio,params],true)

  useEffect(() => { if (metadata.data?.defaults) setParams(old=>({...metadata.data.defaults,...old})) }, [metadata.data])
  useEffect(()=>{setWorkspace(old=>({...old,singleDraft:{market,family,params,trainRatio}}))},[market,family,params,trainRatio])
  useEffect(()=>{
    if(job?.status!=='completed'||result)return
    let cancelled=false;const generation=actionGeneration.current
    api.singleResult(job.job_id).then(value=>{if(!cancelled&&generation===actionGeneration.current)setResult(value)}).catch(error=>{if(!cancelled)setFormError(error.message)})
    return ()=>{cancelled=true}
  },[job?.job_id])
  useEffect(() => {
    if (!job?.job_id || ['complete','completed','failed','error'].includes(job.status)) return
    let cancelled=false
    const frozen={job_id:job.job_id,symbol:job.symbol,family:job.family,dataset_id:job.dataset_id}
    const timer = setInterval(async () => {
      try {
        const next = await api.singleJob(frozen.job_id)
        if(cancelled)return
        const completed=['complete','completed','succeeded','success'].includes(next.status)
        const payload=completed?await api.singleResult(frozen.job_id):null
        if(cancelled)return
        const tracked={...next,...frozen,display_label:payload?.artifact?.display_label||frozen.family}; setJob(tracked); addSingleJob(tracked)
        if(payload)setResult(payload)
      } catch (error) { if(!cancelled)setJob((old) => old?.job_id===frozen.job_id?({ ...old, status: 'error', error: error.message }):old) }
    }, 1000)
    return () => {cancelled=true;clearInterval(timer)}
  }, [job?.job_id, job?.status])

  const loadSelected = async (choice=selected) => {
    if (!choice) return; const generation=++actionGeneration.current; setFormError(''); setDataBusy(true); setResult(null); setJob(null)
    try { const base = await api.loadStock({ market, symbol: choice.symbol, adjust, force_refresh:forceRefresh }); const loaded=(startDate||endDate)?await api.sliceDataset(base.dataset_id,{start_date:startDate||null,end_date:endDate||null}):base; loaded.name=choice.name; if(generation!==actionGeneration.current)return; setDataset(loaded); addDataset(loaded); setWorkspace(old=>({...old,singleDatasetId:loaded.dataset_id})); setView('analysis'); setSection('basics'); setCompareIds([]); setCompareSeries([]); setResultView('workspace'); setFamily('') }
    catch (error) { if(generation===actionGeneration.current)setFormError(error.message) } finally { if(generation===actionGeneration.current)setDataBusy(false) }
  }
  const upload = async (file) => {
    if (!file) return; const generation=++actionGeneration.current; setDataBusy(true); setFormError(''); setResult(null); setJob(null)
    try { const base = await api.uploadStock(file, { market, adjust, symbol: file.name.replace(/\.csv$/i, '') }); const loaded=(startDate||endDate)?await api.sliceDataset(base.dataset_id,{start_date:startDate||null,end_date:endDate||null}):base; if(generation!==actionGeneration.current)return; setDataset(loaded); addDataset(loaded); setWorkspace(old=>({...old,singleDatasetId:loaded.dataset_id})); setView('analysis'); setSection('basics'); setCompareIds([]); setCompareSeries([]); setResultView('workspace'); setFamily('') }
    catch (error) { if(generation===actionGeneration.current)setFormError(error.message) } finally { if(generation===actionGeneration.current)setDataBusy(false) }
  }
  const runAnalysis = async () => {
    if (!family) return setFormError(zh?'请选择模型家族':'Select a model family')
    if (!dataset?.dataset_id) return setFormError(zh ? '请先加载行情数据。' : 'Load market data first.')
    const generation=++actionGeneration.current; setDataBusy(true); const frozen={symbol:dataset.symbol,family,dataset_id:dataset.dataset_id}; setFormError(''); setResult(null)
    try {
      const request = { family }
      if (family === 'baseline') request.baseline_kind = baselineKind
      if (family === 'regime') request.regime_kind = regimeKind
      if (family === 'composite') request.composite_policy = compositePolicy
      if (family === 'search') { request.search_base = searchBase; request.use_search = useParameterSearch; if(useParameterSearch){request.search_method = searchMethod;request.search_trials=searchTrials} }
      request.use_ml=family==='search'&&useMl; request.use_news=family==='search'&&useNews
      if(family==='search'&&useMl){ request.ml_model_type=mlModel; request.ml_horizon_days=mlHorizon; request.ml_min_excess_samples=20 }
      if(family==='search'&&useNews){ request.news_weight=newsWeight; request.news_lookback=newsLookback }
      if(family==='composite'){ request.composite_risk_budget=riskBudget; request.composite_position_method=positionMethod }
      const created = await api.createSingleJob({ dataset_id: dataset.dataset_id, train_ratio: trainRatio, request, params })
      if(generation!==actionGeneration.current)return
      const tracked={...created,...frozen}; setJob(tracked); addSingleJob(tracked)
    } catch (error) { if(generation===actionGeneration.current)setFormError(error.message) } finally { if(generation===actionGeneration.current)setDataBusy(false) }
  }
  const openSavedJob = async (id, row) => {
    const generation = ++actionGeneration.current
    setJob(null); setResult(null); setFormError(''); setDataBusy(true)
    try {
      const current = await api.singleJob(id)
      if (generation !== actionGeneration.current) return
      const payload = current.status === 'completed' ? await api.singleResult(id) : null
      if (generation !== actionGeneration.current) return
      setJob({ ...row, ...current }); setResult(payload); if(payload)addSingleJob({...row,...current,display_label:payload.artifact?.display_label})
      requestAnimationFrame(() => document.querySelector('.job-progress,.result-board')?.scrollIntoView({ block: 'start' }))
    } catch (error) {
      if (generation === actionGeneration.current) setFormError(error.message)
    } finally {
      if (generation === actionGeneration.current) setDataBusy(false)
    }
  }
  const applyRange = async () => {
    if(!dataset?.dataset_id)return
    const generation=++actionGeneration.current;setDataBusy(true);setFormError('')
    try { const next=await api.sliceDataset(dataset.dataset_id,{start_date:startDate||null,end_date:endDate||null});if(generation!==actionGeneration.current)return;setDataset(next);addDataset(next);setWorkspace(old=>({...old,singleDatasetId:next.dataset_id}));setResult(null);setJob(null);setCompareIds([]);setCompareSeries([]) }
    catch(error){if(generation===actionGeneration.current)setFormError(error.message)}finally{if(generation===actionGeneration.current)setDataBusy(false)}
  }
  const currentJobs=workspace.singleJobs.filter(row=>row.dataset_id===dataset?.dataset_id&&(row.job_id===job?.job_id||(workspace.savedSingleJobIds||[]).includes(row.job_id)))
  const summary=basics.data?.summary
  if(view==='entry') return <SingleEntry zh={zh} market={market} setMarket={setMarket} query={query} setQuery={setQuery} selected={selected} setSelected={setSelected} adjust={adjust} setAdjust={setAdjust} startDate={startDate} setStartDate={setStartDate} endDate={endDate} setEndDate={setEndDate} loadSelected={loadSelected} upload={upload} busy={dataBusy} error={formError} onResume={dataset?()=>setView('analysis'):null}/>
  return <main id="main" className="page single-analysis">
    <header className="single-context"><div><h1>{dataset?.name||dataset?.symbol}</h1><p>{dataset?.symbol} · {dataset?.market==='CN_A'?(zh?'A 股':'China A shares'):(zh?'美股':'US stocks')} · {zh?'单股策略分析':'Single-stock strategy analysis'}</p></div><div className="single-date-range"><Field label={zh?'开始日期':'Start date'}><input type="date" value={startDate} onChange={e=>setStartDate(e.target.value)}/></Field><Field label={zh?'结束日期':'End date'}><input type="date" value={endDate} onChange={e=>setEndDate(e.target.value)}/></Field><Button variant="secondary" disabled={dataBusy} onClick={()=>applyRange()}>{zh?'应用区间':'Apply range'}</Button></div><button className="text-button" onClick={()=>setShowDetails(!showDetails)}>{showDetails?(zh?'收起详情':'Hide details'):(zh?'展开详情':'Show details')}</button></header>
    {showDetails&&<div className="metric-grid"><Metric label={zh?'最新收盘价':'Latest close'} value={summary?.latest_price?.toFixed(2)}/><Metric label={zh?'训练 / 测试':'Train / test'} value={summary?`${summary.train_rows} / ${summary.test_rows}`:'N/A'}/><Metric label={zh?'数据范围':'Data range'} value={formatDateRange(dataset?.date_range)}/></div>}
    <details className="single-global-params"><summary>{zh?'指标与策略参数':'Indicator and strategy parameters'}</summary><div className="form-grid compact">{Object.entries(params).map(([key,value])=><ParamField key={key} name={key} value={value} onChange={next=>setParams({...params,[key]:next})}/>)}</div></details>
    <div className="single-section-nav"><Segments label={zh?'分析区域':'Analysis section'} value={section} onChange={setSection} options={[['basics',zh?'基础信息':'Basic information'],['strategy',zh?'策略':'Strategy']]}/><Button variant="secondary" onClick={()=>setView('entry')}>{zh?'切换股票':'Switch stock'}</Button></div>
    {formError&&<Status state="error">{formError}</Status>}
    {section==='basics'?<SingleBasics zh={zh} resource={basics} period={period} setPeriod={setPeriod} scope={scope} setScope={setScope} indicator={indicator} setIndicator={setIndicator}/>:<>
      <h2>{zh?'策略区':'Strategy workspace'}</h2>
      <div className="single-workbench"><aside className="single-console"><h3>{zh?'模型控制台':'Model console'}</h3><details><summary>{zh?'如何使用策略模块':'How to use the strategy module'}</summary><p>{zh?'选择模型家族并配置参数，生成当前策略后可保存到策略库，选择多个策略进行对比。训练集用于拟合与选参，测试集用于评估。':'Choose a family and configure its parameters. Generate and save strategies to compare them. Training data is used for fitting and selection; test data is used for evaluation.'}</p></details>
      <div className="strategy-form">
        {metadata.status==='loading'&&<Status state="loading">{zh?'正在加载策略参数':'Loading strategy parameters'}</Status>}
        {metadata.status==='error'&&<Status state="error" onRetry={metadata.run}>{metadata.error?.message}</Status>}
        <div className="family-tabs" role="radiogroup" aria-label={zh ? '策略家族' : 'Strategy family'}>{Object.keys(metadata.data?.strategy_families || {}).length ? Object.keys(metadata.data.strategy_families).filter(v=>v!=='regime'||dataset?.market==='US').map((value) => <button key={value} role="radio" aria-checked={family === value} onClick={() => setFamily(value)}>{value}</button>) : families.map((value) => <button key={value} role="radio" aria-checked={family === value} onClick={() => setFamily(value)}>{value}</button>)}</div>
        <div className="form-grid">
          {family === 'baseline' && <Field label="Baseline"><select value={baselineKind} onChange={(e) => setBaselineKind(e.target.value)}>{baselineKinds.map((v) => <option key={v}>{v}</option>)}</select></Field>}
          {family === 'regime' && <Field label="Regime router"><select value={regimeKind} onChange={(e) => setRegimeKind(e.target.value)}><option value="adaptive_router_v1">adaptive_router_v1</option><option value="dual_state_router">dual_state_router</option><option value="no_market">no_market</option><option value="no_router">no_router</option></select></Field>}
          {family === 'composite' && <Field label="Composite policy"><select value={compositePolicy} onChange={(e) => setCompositePolicy(e.target.value)}>{compositePolicies.map((v) => <option key={v}>{v}</option>)}</select></Field>}
          {family === 'composite' && <><Field label={zh?'风险预算':'Risk budget'}><input type="range" min="0.1" max="1" step="0.1" value={riskBudget} onChange={e=>setRiskBudget(Number(e.target.value))}/><small>{riskBudget.toFixed(1)}</small></Field><Field label={zh?'仓位映射':'Position mapping'}><select value={positionMethod} onChange={e=>setPositionMethod(e.target.value)}><option value="linear_clip">linear_clip</option><option value="tanh_smooth">tanh_smooth</option><option value="quantile_5bin">quantile_5bin</option></select></Field></>}
          {family === 'search' && <><Field label={zh ? '策略基础' : 'Strategy base'}><select value={searchBase} onChange={(e) => setSearchBase(e.target.value)}><option value="sm">SM</option><option value="fsm">FSM</option></select></Field><Field label={zh?'参数优化':'Parameter search'}><span className="check-row"><label><input type="checkbox" checked={useParameterSearch} onChange={e=>setUseParameterSearch(e.target.checked)}/>{zh?'启用搜索':'Enable search'}</label></span></Field>{useParameterSearch&&<><Field label={zh ? '搜索方法' : 'Search method'}><select value={searchMethod} onChange={(e) => setSearchMethod(e.target.value)}><option value="bayesian">bayesian</option><option value="random">random</option><option value="genetic">genetic</option></select></Field><Field label={zh?'搜索次数':'Search trials'}><input type="number" min="1" max="240" value={searchTrials} onChange={e=>setSearchTrials(Number(e.target.value))}/></Field></>}</>}
          <Field label={zh ? '训练比例' : 'Train ratio'} hint={`${Math.round(trainRatio * 100)}% train / ${Math.round((1-trainRatio)*100)}% test`}><input type="range" min="0.6" max="0.9" step="0.05" value={trainRatio} onChange={(e) => setTrainRatio(Number(e.target.value))} /></Field>
          {family==='search'&&<Field label={zh?'增强模块':'Enhancements'}><span className="check-row"><label><input type="checkbox" checked={useMl} onChange={e=>setUseMl(e.target.checked)}/> ML</label><label><input type="checkbox" checked={useNews} onChange={e=>setUseNews(e.target.checked)}/> News</label></span></Field>}
          {family==='search'&&useMl&&<><Field label={zh?'ML 模型':'ML model'}><select value={mlModel} onChange={e=>setMlModel(e.target.value)}><option value="logistic">logistic</option><option value="lgbm">lgbm</option></select></Field><Field label={zh?'预测周期':'ML horizon'}><input type="number" min="1" max="252" value={mlHorizon} onChange={e=>setMlHorizon(Number(e.target.value))}/></Field></>}
          {family==='search'&&useNews&&<><Field label={zh?'新闻权重':'News weight'}><input type="number" min="0" max="2" step="0.1" value={newsWeight} onChange={e=>setNewsWeight(Number(e.target.value))}/></Field><Field label={zh?'新闻回看':'News lookback'}><input type="number" min="2" max="252" value={newsLookback} onChange={e=>setNewsLookback(Number(e.target.value))}/></Field></>}
        </div>
        <details><summary>{zh ? '高级指标与风控参数' : 'Advanced indicator and risk parameters'}</summary><div className="form-grid compact">{Object.entries(params).map(([key, value]) => <ParamField key={key} name={key} value={value} onChange={(next) => setParams({ ...params, [key]: next })}/>)}</div></details>
        <Button onClick={runAnalysis} disabled={!family || !dataset || dataBusy || metadata.status!=='success' || ['queued','running'].includes(job?.status)}>{zh ? '生成策略' : 'Generate strategy'}</Button>
        {job && !result && <div className="job-progress"><div><span>{zh ? '计算状态' : 'Computation status'}</span><strong>{job.status}</strong></div><progress value={(job.progress || 0) * 100} max={100} /><small>{Math.round((job.progress || 0) * 100)}%</small>{job.error && <Status state="error">{job.error}</Status>}</div>}
      </div>

        <h3>{zh?'策略库':'Strategy library'}</h3>
        <Button variant="secondary" disabled={!result||job?.status!=='completed'||(workspace.savedSingleJobIds||[]).includes(job?.job_id)} onClick={()=>setWorkspace(old=>({...old,savedSingleJobIds:[...new Set([...(old.savedSingleJobIds||[]),job.job_id])]}))}>{(workspace.savedSingleJobIds||[]).includes(job?.job_id)?(zh?'已保存':'Saved'):(zh?'保存当前策略':'Save current strategy')}</Button>
        <p className="caption">{zh?'当前标的已生成的策略，可打开或选择进行对比。':'Generated strategies for this dataset. Open a result or select strategies to compare.'}</p>
        {currentJobs.length===0&&<Status>{zh?'尚未生成策略':'No strategies generated'}</Status>}
        {currentJobs.map(row=><div className="strategy-library-row" key={row.job_id}><label><input type="checkbox" disabled={row.status!=='completed'} checked={compareIds.includes(row.job_id)} onChange={e=>setCompareIds(e.target.checked?[...compareIds,row.job_id]:compareIds.filter(id=>id!==row.job_id))}/>{row.symbol} · {row.display_label||row.family}<small>{row.status}</small></label><button className="table-action" disabled={dataBusy} onClick={()=>openSavedJob(row.job_id,row)}>{zh?'打开':'Open'}</button></div>)}
        <Button variant="secondary" disabled={dataBusy||compareIds.length<2} onClick={async()=>{const generation=++actionGeneration.current;try{const ids=compareIds.filter(id=>currentJobs.some(row=>row.job_id===id));const values=await Promise.all(ids.map(id=>api.singleResult(id)));if(generation!==actionGeneration.current)return;setCompareSeries(values.map((value,i)=>({id:ids[i],artifact:value.artifact,name:value.artifact?.display_label||ids[i].slice(0,6),data:value.artifact?.equity,valueKey:'equity'})));setResultView('compare')}catch(e){setFormError(e.message)}}}>{zh?'比较所选策略':'Compare selected strategies'}</Button>
      </aside><section className="single-results"><Segments label={zh?'结果视图':'Result view'} value={resultView} onChange={setResultView} options={[['workspace',zh?'当前策略':'Current strategy'],['compare',zh?'策略对比':'Strategy comparison']]}/>
        {resultView==='compare'?(compareSeries.length>1?<StrategyComparison entries={compareSeries} zh={zh}/>:<Status>{zh?'从左侧策略库选择至少两个策略。':'Select at least two strategies from the library.'}</Status>):result?<ResultBoard key={job?.job_id} result={result} zh={zh} jobId={job?.job_id}/>:<Status state={job?.status==='failed'?'error':job?.status==='running'?'loading':'empty'}>{job?.error||(zh?'尚未生成策略。请在左侧选择模型家族，完成配置后生成策略。':'No strategy generated. Choose a family and configure it in the left panel, then generate a strategy.')}</Status>}
      </section></div></>}
  </main>
}

function ResultBoard({ result, zh, jobId }) {
  const artifact = result?.artifact || result || {}; const metrics = artifact.metrics || {}; const equity = artifact.equity || []; const returns = artifact.returns || []
  const trades = Array.isArray(artifact.trades) ? artifact.trades : []; const signals = Array.isArray(artifact.signals) ? artifact.signals : []
  const [detail,setDetail]=useState('signals');
  const [split,setSplit]=useState('test'); const splitRows=artifact[split]||[]; const diagnostics=artifact.diagnostics?.test||{}; const splitDates=new Set(splitRows.map(row=>row.date))
  const metricLabels={cumret:zh?'累计收益':'Cumulative return',annret:zh?'年化收益':'Annual return',maxdd:zh?'最大回撤':'Max drawdown',sharpe:zh?'夏普比率':'Sharpe ratio',bench_cumret:zh?'基准累计收益':'Benchmark return',bench_annret:zh?'基准年化收益':'Benchmark annual return',bench_maxdd:zh?'基准最大回撤':'Benchmark drawdown',bench_sharpe:zh?'基准夏普':'Benchmark Sharpe',excess_return:zh?'超额收益':'Excess return',winrate:zh?'胜率':'Win rate',pnl_ratio:zh?'盈亏比':'Profit/loss ratio',avg_hold:zh?'平均持仓期':'Average holding',turnover:zh?'换手率':'Turnover'}
  const percentKeys=new Set(['cumret','annret','maxdd','bench_cumret','bench_annret','bench_maxdd','excess_return','winrate','turnover'])
  const fmt = (key,value) => typeof value === 'number' ? (percentKeys.has(key)?value.toLocaleString(undefined,{style:'percent',maximumFractionDigits:2}):value.toLocaleString(undefined,{maximumFractionDigits:3})) : value ?? 'N/A'
  return <div className="result-board">
    <div className="result-toolbar"><span className={`pill pill-${result?.status || 'complete'}`}>{result?.status || 'complete'}</span>{jobId && <a className="button button-secondary" href={`${api.singleExportUrl(jobId)}?language=${zh?'zh':'en'}`} download><Download size={16} />{zh ? '下载 HTML' : 'Download HTML'}</a>}</div>
    {result?.warnings?.length > 0 && <Status state="error">{result.warnings.join(' · ')}</Status>}
    <ResultSummary artifact={artifact} zh={zh} />
    <h3>{zh?'测试集绩效':'Test-set performance'}</h3><div className="metric-grid featured">{Object.entries(metrics).filter(([key])=>key!=='label').map(([key, value]) => <Metric key={key} label={metricLabels[key]||key.replaceAll('_',' ')} value={fmt(key,value)} />)}</div>
    <details><summary>{zh ? '全部绩效指标' : 'All performance metrics'}</summary><DataTable rows={Object.entries(metrics).filter(([key])=>key!=='label').map(([key,value])=>({metric:metricLabels[key]||key.replaceAll('_',' '),value:fmt(key,value)}))} columns={[{key:'metric',label:zh?'指标':'Metric'},{key:'value',label:zh?'值':'Value'}]} /></details>

    <div className="result-tabs">
      <h3>{zh?'当前策略净值与回撤':'Current equity and drawdown'}</h3><LineChart series={[{name:zh?'策略净值':'Strategy equity',data:artifact.test||[],valueKey:'strategy_equity'},{name:zh?'买入持有':'Buy & hold',data:artifact.test||[],valueKey:'buy_hold_equity'}]} name="Equity" />
<section>{diagnostics.drawdown?<LineChart series={diagnostics.drawdown} valueKey="drawdown" name="Drawdown" color="#bb513d" percent height={260}/>:<DrawdownChart equity={equity} />}</section>
      <h3>{zh?'月度收益':'Monthly returns'}</h3><MonthlyHeatmap rows={diagnostics.monthly_returns||[]} />
      <Segments label={zh?'详细结果':'Detailed results'} value={detail} onChange={setDetail} options={[["signals",zh?'买卖点':'Trading signals'],['walk_forward',zh?'滚动检验':'Walk-forward'],['ml',zh?'ML 质量':'ML quality']]}/>
      {detail==='signals'&&<>    <div className="family-tabs" role="radiogroup" aria-label={zh?'买卖点数据区间':'Signal data split'}><button role="radio" aria-checked={split==='train'} onClick={()=>setSplit('train')}>{zh?'训练集':'Train'}</button><button role="radio" aria-checked={split==='test'} onClick={()=>setSplit('test')}>{zh?'测试集':'Test'}</button></div><CandleChart rows={signals.filter(row=>splitDates.has(row.date))} /></>}
      <details><summary>{zh ? '交易记录' : 'Trades'}</summary><DataTable rows={trades.slice(-200).reverse()} columns={inferColumns(trades)} empty={zh ? '暂无交易记录' : 'No trades'} /></details>
      <details><summary>{zh ? '交易信号' : 'Signals'}</summary><DataTable rows={signals.slice(-200).reverse()} columns={inferColumns(signals)} empty={zh ? '暂无信号' : 'No signals'} /></details>
      {detail==='walk_forward'&&<WalkForward jobId={jobId} zh={zh}/>}
      {detail==='ml'&&(artifact.ml_quality?<DataTable rows={Object.entries(artifact.ml_quality).map(([key,value])=>({key,value:typeof value==='object'?JSON.stringify(value):String(value)}))} columns={[{key:'key',label:zh?'指标':'Metric'},{key:'value',label:zh?'值':'Value'}]}/>:<Status>{zh?'当前策略未启用 ML 过滤器，暂无质量评估。':'No ML quality evaluation is available for this strategy.'}</Status>)}
      <FactorScorePanel artifact={artifact} split={split} zh={zh} />
    </div>
  </div>
}

function inferColumns(rows) { return Object.keys(rows?.[0] || {}).slice(0, 8).map((key) => ({ key, label: key.replaceAll('_',' ') })) }
function formatDateRange(value) { if (!value) return 'N/A'; if (Array.isArray(value)) return value.join(' — '); if (typeof value === 'object') return `${value.start || 'N/A'} — ${value.end || 'N/A'}`; return String(value) }
function ParamField({name,value,onChange}) { if(typeof value==='boolean') return <Field label={name.replaceAll('_',' ')}><input type="checkbox" checked={value} onChange={e=>onChange(e.target.checked)}/></Field>; if(typeof value==='number') return <Field label={name.replaceAll('_',' ')}><input type="number" step="any" value={value} onChange={e=>onChange(Number(e.target.value))}/></Field>; return <Field label={name.replaceAll('_',' ')}><input type="text" value={value ?? ''} onChange={e=>onChange(e.target.value)}/></Field> }

function WalkForward({jobId,zh,mlQuality}) {
  const [train,setTrain]=useState(252); const [test,setTest]=useState(63); const wf=useAsync(()=>api.walkForward(jobId,train,test),[jobId,train,test],false)
  return <details open><summary>{zh?'滚动检验':'Walk-forward'}</summary><p className="caption">{zh?'滚动窗口复现既有信号，不会在每个窗口重新训练模型。':'Rolling windows replay existing signals; the model is not retrained inside each window.'}</p><div className="form-grid"><Field label={zh?'训练窗口':'Train window'}><input type="number" min="20" value={train} onChange={e=>setTrain(Number(e.target.value))}/></Field><Field label={zh?'测试窗口':'Test window'}><input type="number" min="5" value={test} onChange={e=>setTest(Number(e.target.value))}/></Field></div><Button variant="secondary" onClick={()=>wf.run()}>{zh?'运行滚动检验':'Run walk-forward'}</Button>{wf.status==='loading'&&<Status state="loading">{zh?'正在计算':'Calculating'}</Status>}{wf.status==='error'&&<Status state="error">{wf.error?.message}</Status>}{wf.data&&<><LineChart series={wf.data.equity} name="Walk-forward equity"/><DataTable rows={wf.data.windows||[]} columns={inferColumns(wf.data.windows||[])}/></>} {mlQuality&&<pre className="json-view">{JSON.stringify(mlQuality,null,2)}</pre>}</details>
}
