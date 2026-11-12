import { Fragment, useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import { FigureChart } from '../components/Charts'
import { Status } from '../components/Primitives'
import { useAsync } from '../hooks/useAsync'
import { useApp } from '../state/AppContext'
import { useReadingSection } from '../hooks/useReadingSection'
import { markdownBlocks, safeMarkdownHref } from './reader-markdown'
import './reader.css'

const STATUS_LABELS = {
  baseline_frozen: ['基线已冻结', 'Baseline frozen'],
  passed_research_gate: ['通过研究准入', 'Research gate passed'],
  framework_complete_pending_real_data_gate: ['框架完成，等待真实数据准入', 'Framework complete; real-data gate pending'],
  stopped: ['已停止', 'Stopped'],
  not_admitted: ['未准入', 'Not admitted'],
  completed: ['已完成（研究可选）', 'Completed (research optional)'],
}

const SECTION_GROUPS = [
  [['frozen scope', 'scope', 'hypothesis'], ['研究计划与范围', 'Plan and frozen scope']],
  [['research flow', 'workflow'], ['研究流程', 'Research flow']],
  [['key decisions and ideas', 'decisions'], ['重要决策与关键想法', 'Decisions and key ideas']],
  [['result and current status', 'result'], ['结果与图表', 'Results and charts']],
  [['gate and current status', 'gate and stop conditions', 'gate'], ['Gate：在哪里停下或放行', 'Gate: where it stopped or passed']],
  [['problems and future work', 'problems and future remedies', 'problems'], ['问题、卡点与未来解决方法', 'Problems, blockers and future remedies']],
]

function statusLabel(status, zh) {
  return STATUS_LABELS[status]?.[zh ? 0 : 1] || status?.replaceAll('_', ' ') || '—'
}

function sectionsFromMarkdown(markdown = '') {
  const result = {}
  let key = ''
  markdown.split(/\r?\n/).forEach((line) => {
    const heading = line.match(/^##\s+(.+)$/)
    if (heading) {
      key = heading[1].trim().toLowerCase()
      result[key] = []
    } else if (key) result[key].push(line)
  })
  return Object.fromEntries(Object.entries(result).map(([name, lines]) => [name, lines.join('\n').trim()]))
}

function sectionValue(sections, aliases) {
  const entry = Object.entries(sections).find(([name]) => aliases.some((alias) => name.includes(alias)))
  return entry?.[1] || ''
}

function inlineMarkdown(text) {
  const tokens = String(text).split(/(`[^`]+`|\[[^\]]+\]\([^)]+\)|\*\*[^*]+\*\*)/g).filter(Boolean)
  return tokens.map((token, index) => {
    if (token.startsWith('`') && token.endsWith('`')) return <code key={index}>{token.slice(1, -1)}</code>
    const link = token.match(/^\[([^\]]+)\]\(([^)]+)\)$/)
    if (link) {
      const href = safeMarkdownHref(link[2])
      return href ? <a key={index} href={href} {...(/^https?:/i.test(href) ? { target: '_blank', rel: 'noreferrer' } : {})}>{link[1]}</a> : <span key={index}>{link[1]}</span>
    }
    if (token.startsWith('**') && token.endsWith('**')) return <strong key={index}>{token.slice(2, -2)}</strong>
    return token
  })
}

function MarkdownBody({ text, empty }) {
  if (!text) return <p className="reader-empty">{empty}</p>
  return <div className="reader-markdown">{markdownBlocks(text).map((block, index) => {
    if (block.type === 'code') return <pre key={index}><code className={block.language ? `language-${block.language}` : undefined}>{block.body}</code></pre>
    if (block.type === 'heading') { const Heading = `h${Math.min(6, block.level + 2)}`; return <Heading key={index}>{inlineMarkdown(block.body)}</Heading> }
    if (block.type === 'table') return <div className="reader-table-wrap" key={index}><table><thead><tr>{block.head.map((cell, cellIndex) => <th key={cellIndex}>{inlineMarkdown(cell)}</th>)}</tr></thead><tbody>{block.rows.map((row, rowIndex) => <tr key={rowIndex}>{row.map((cell, cellIndex) => <td key={cellIndex}>{inlineMarkdown(cell)}</td>)}</tr>)}</tbody></table></div>
    if (block.type === 'ul' || block.type === 'ol') { const List = block.type; return <List key={index}>{block.items.map((item, itemIndex) => <li key={itemIndex}>{inlineMarkdown(item)}</li>)}</List> }
    if (block.type === 'quote') return <blockquote key={index}>{inlineMarkdown(block.body)}</blockquote>
    return <p key={index}>{inlineMarkdown(block.body)}</p>
  })}</div>
}

function MetricGrid({ experiment, zh }) {
  const results = Object.entries(experiment.key_results || {}).slice(0, 3)
  const available = (experiment.evidence || []).filter((entry) => entry.available).length
  const items = [
    [zh ? '研究状态' : 'Status', statusLabel(experiment.status, zh), zh ? '研究档案状态' : 'Research archive status'],
    [zh ? '市场' : 'Markets', (experiment.markets || []).join(', ') || '—', zh ? '结论独立于市场' : 'Market-local conclusions'],
    [zh ? '证据' : 'Evidence', `${available}/${experiment.evidence?.length || 0}`, zh ? '当前文件可用性' : 'Current file availability'],
    ...results.map(([key, value]) => [key.replaceAll('_', ' '), Array.isArray(value) ? value.join(', ') : String(value), zh ? '目录记录' : 'Catalog record']),
  ]
  return <div className="reader-metrics">{items.map(([label, value, meta]) => <div key={label}><span>{label}</span><strong>{value}</strong><small>{meta}</small></div>)}</div>
}

function EvidenceLedger({ experiment, zh }) {
  return <section className="reader-subsection evidence-ledger">
    <h3>{zh ? '证据账本' : 'Evidence ledger'}</h3>
    <div className="reader-table-wrap"><table><thead><tr><th>{zh ? '路径' : 'Path'}</th><th>{zh ? '状态' : 'State'}</th><th>{zh ? '类型' : 'Kind'}</th></tr></thead><tbody>
      {(experiment.evidence || []).map((entry) => <tr key={entry.path}><td><code>{entry.path}</code></td><td><span className={`evidence-state ${entry.available ? 'available' : 'pending'}`}>{entry.available ? (zh ? '可用' : 'Available') : (zh ? '待补' : 'Pending')}</span></td><td>{entry.required ? (zh ? '必需' : 'Required') : (zh ? '可选' : 'Optional')}</td></tr>)}
    </tbody></table></div>
    <details><summary>{zh ? '源文件' : 'Source files'}</summary><ul className="source-list">{(experiment.sources || []).map((source) => <li key={source}><code>{source}</code></li>)}</ul></details>
  </section>
}

function ExperimentChapter({ experiment, detail, zh, register }) {
  const data = detail?.data || experiment
  const sections = useMemo(() => sectionsFromMarkdown(data.readme), [data.readme])
  const missingRequired = (data.evidence || []).some((entry) => entry.required && !entry.available)
  const chart = data.chart
  const chartEdition = chart?.editions?.[zh ? 'zh' : 'en']
  return <article ref={register} id={`research-${experiment.id}`} className="research-chapter" tabIndex="-1">
    <header className="research-chapter-heading"><div><h2>{zh ? data.localized_zh?.title || data.title : data.title}</h2><p>{zh ? data.localized_zh?.question || data.question : data.question}</p></div><span className={`research-status ${data.status}`}>{statusLabel(data.status, zh)}</span></header>
    {detail?.status === 'loading' && <Status state="loading">{zh ? '正在读取研究档案' : 'Loading research archive'}</Status>}
    {detail?.status === 'error' && <Status state="error">{detail.error?.message}</Status>}
    <MetricGrid experiment={data} zh={zh} />
    {missingRequired && <p className="reader-warning">{zh ? '至少一份必需机器证据当前缺失；请勿把这条历史记录当作当前可复核的准入证明。' : 'At least one required machine-readable artifact is missing; do not treat this historical record as currently verifiable admission evidence.'}</p>}
    {SECTION_GROUPS.map(([aliases, labels]) => {
      const localizedKey = ({ 'frozen scope': 'scope', 'research flow': 'flow', 'key decisions and ideas': 'decisions', 'result and current status': 'result', 'gate and current status': 'gate', 'problems and future work': 'problems' })[aliases[0]]
      const text = zh ? data.localized_zh?.[localizedKey] : sectionValue(sections, aliases)
      return <Fragment key={aliases[0]}><section className="reader-subsection"><h3>{labels[zh ? 0 : 1]}</h3><MarkdownBody text={text || (localizedKey === 'gate' ? data.gate : '')} empty={zh ? '此记录没有单独段落。' : 'No separate section is recorded.'} /></section>
        {localizedKey === 'result' && chart?.available && chartEdition && <section className="reader-subsection research-chart"><h3>{chartEdition.title}</h3><FigureChart figure={chartEdition.figure} name={chartEdition.title} /><p className="research-chart-source">{chart.supplemental ? (zh ? '补充诊断来源（不等于 canonical gate 证据）' : 'Supplemental diagnostic source (not canonical gate evidence)') : (zh ? '真实来源' : 'Real source')}: <code>{chart.source}</code></p>{chart.supplemental && <p className="reader-warning">{zh ? '这张图使用已有补充产物帮助理解研究过程；它不会替代目录中声明的必需 manifest / ablation gate。' : 'This chart uses an existing supplemental artifact to explain the process; it does not replace the required manifest/ablation gate declared by the catalog.'}</p>}</section>}
        {localizedKey === 'result' && chart && !chart.available && <p className="reader-warning">{chart.message?.[zh ? 'zh' : 'en']}</p>}
      </Fragment>
    })}
    {Object.keys(data.key_results || {}).length > 0 && <section className="reader-subsection"><h3>{zh ? '关键结果' : 'Key results'}</h3><div className="reader-table-wrap"><table><tbody>{Object.entries(data.key_results).map(([key, value]) => <tr key={key}><th>{key.replaceAll('_', ' ')}</th><td>{Array.isArray(value) ? value.join(', ') : String(value)}</td></tr>)}</tbody></table></div></section>}
    <EvidenceLedger experiment={data} zh={zh} />
  </article>
}

export function ResearchPage() {
  const { language } = useApp()
  const zh = language === 'zh'
  const catalog = useAsync(() => api.researchCatalog(), [], true)
  const reports = useAsync(async () => {
    const experiments = catalog.data?.experiments || []
    const settled = await Promise.allSettled(experiments.map((item) => api.researchReport(item.id)))
    return Object.fromEntries(experiments.map((item, index) => [item.id, settled[index].status === 'fulfilled'
      ? { status: 'success', data: settled[index].value, error: null }
      : { status: 'error', data: null, error: settled[index].reason }]))
  }, [catalog.data], catalog.status === 'success')
  const [query, setQuery] = useState('')
  const [active, setActive] = useState(() => new URLSearchParams(window.location.search).get('experiment'))
  const items = catalog.data?.experiments || []
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase()
    return needle ? items.filter((item) => JSON.stringify(reports.data?.[item.id]?.data || item).toLowerCase().includes(needle)) : items
  }, [items, query, reports.data])
  const readingIds = useMemo(() => filtered.map((item) => `research-${item.id}`), [filtered])
  const readingSection = useReadingSection(readingIds)
  const visibleActive = readingSection?.replace(/^research-/, '') || active

  useEffect(() => { if (!active && filtered[0]) setActive(filtered[0].id) }, [active, filtered])
  const select = (id) => {
    setActive(id)
    const url = new URL(window.location.href)
    url.searchParams.set('experiment', id)
    url.hash = `research-${id}`
    history.replaceState({}, '', url)
    requestAnimationFrame(() => document.getElementById(`research-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' }))
  }

  return <main id="main" className="page reader-page research-reader">
    <header className="reader-title"><p>{zh ? '研究证据' : 'Research evidence'}</p><h1>{zh ? '从基线到 Composite：完整研究报告' : 'From baseline to Composite: the complete research report'}</h1></header>
    <label className="reader-search"><span>{zh ? '搜索研究：实验名、结论、gate、文件路径或指标' : 'Search research: title, conclusion, gate, path or metric'}</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={zh ? '例如：Composite、Transformer、drawdown、pending' : 'e.g. Composite, Transformer, drawdown, pending'} /></label>
    {catalog.status === 'loading' && <Status state="loading">{zh ? '正在读取研究目录' : 'Loading research catalog'}</Status>}
    {catalog.status === 'error' && <Status state="error" onRetry={catalog.run}>{catalog.error?.message}</Status>}
    {catalog.status === 'success' && !filtered.length && <Status>{zh ? '没有匹配的实验；请尝试 Composite、advisory、gate 或文件名。' : 'No experiment matched. Try Composite, advisory, gate or a file name.'}</Status>}
    {!!filtered.length && <>
      <nav className="research-flow" aria-label={zh ? '研究目录' : 'Research contents'}>{filtered.map((item, index) => <button key={item.id} className={visibleActive === item.id ? 'active' : ''} aria-current={visibleActive === item.id ? 'location' : undefined} onClick={() => select(item.id)}><span>{String(index + 1).padStart(2, '0')}</span><strong>{zh ? item.localized_zh?.title || item.title : item.title}</strong><small>{statusLabel(item.status, zh)}</small></button>)}</nav>
      <div className="reader-layout"><div className="reader-document">{filtered.map((item) => <ExperimentChapter key={item.id} experiment={item} detail={reports.data?.[item.id] || (reports.status === 'loading' ? { status: 'loading' } : null)} zh={zh} register={(node) => { if (node && active === item.id) node.dataset.active = 'true' }} />)}</div>
        <aside className="reader-rail"><span>{zh ? '本页目录' : 'On this page'}</span><nav>{filtered.map((item) => <button key={item.id} className={visibleActive === item.id ? 'active' : ''} aria-current={visibleActive === item.id ? 'location' : undefined} onClick={() => select(item.id)}>{zh ? item.localized_zh?.title || item.title : item.title}</button>)}</nav></aside>
      </div>
    </>}
  </main>
}
