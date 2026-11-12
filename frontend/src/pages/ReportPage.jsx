import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import { Status } from '../components/Primitives'
import { useAsync } from '../hooks/useAsync'
import { useApp } from '../state/AppContext'
import { ChevronRight } from 'lucide-react'
import { useReadingSection } from '../hooks/useReadingSection'
import './reader.css'

function sanitize(root) {
  root.querySelectorAll('script,style,link,meta,iframe,.search-box').forEach((node) => node.remove())
  root.querySelectorAll('*').forEach((node) => [...node.attributes].forEach((attribute) => {
    if (attribute.name.startsWith('on')) node.removeAttribute(attribute.name)
  }))
}

function parseReport(html) {
  if (!html) return { intro: '', toc: [], chapters: [] }
  const doc = new DOMParser().parseFromString(html, 'text/html')
  sanitize(doc)
  const reportMain = doc.querySelector('main') || doc.body
  const tocNode = reportMain.querySelector('#toc-nav, nav.toc')
  const firstSection = reportMain.querySelector('section')
  const introNodes = [...reportMain.children].filter((node) => node !== tocNode && (!firstSection || node.compareDocumentPosition(firstSection) & Node.DOCUMENT_POSITION_FOLLOWING))
  const intro = introNodes.map((node) => node.outerHTML).join('')
  const chapters = [...reportMain.querySelectorAll(':scope > section')].map((node, index) => {
    const heading = node.querySelector('h1,h2,h3')
    const id = node.id || `chapter-${index + 1}`
    node.id = id
    return { id, title: heading?.textContent?.trim() || `Chapter ${index + 1}`, html: node.outerHTML, text: node.textContent?.replace(/\s+/g, ' ').trim() || '', anchors: [...node.querySelectorAll('[id]')].map((element) => element.id) }
  })
  const toc = [...(tocNode?.querySelectorAll(':scope > ol > li') || [])].map((item, index) => {
    const link = item.querySelector('summary a, :scope > a')
    const children = [...item.querySelectorAll('.sub-toc a')].map((child) => ({ id: child.getAttribute('href')?.slice(1), title: child.textContent.trim() }))
    return { id: link?.getAttribute('href')?.slice(1) || chapters[index]?.id, title: link?.textContent?.trim() || chapters[index]?.title, children }
  }).filter((item) => item.id)
  return { intro, toc, chapters }
}

function snippet(text, query) {
  const index = text.toLowerCase().indexOf(query.toLowerCase())
  return text.slice(Math.max(0, index - 90), Math.min(text.length, index + query.length + 180))
}

export function ReportPage() {
  const { language } = useApp()
  const zh = language === 'zh'
  const report = useAsync(() => api.finalReport(language), [language], true)
  const parsed = useMemo(() => parseReport(typeof report.data === 'string' ? report.data : report.data?.html || ''), [report.data])
  const requested = new URLSearchParams(window.location.search).get('section')
  const defaultChapter = parsed.chapters.find((chapter) => chapter.id.startsWith('section-')) || parsed.chapters[0]
  const [active, setActive] = useState(requested)
  const [expanded, setExpanded] = useState(null)
  const [draft, setDraft] = useState('')
  const [query, setQuery] = useState('')

  useEffect(() => { if (defaultChapter && !parsed.chapters.some((chapter) => chapter.id === active)) setActive(defaultChapter.id) }, [active, defaultChapter, parsed.chapters])
  const choose = (chapterId, anchor = chapterId) => {
    setActive(chapterId)
    setQuery('')
    setDraft('')
    const url = new URL(window.location.href)
    url.searchParams.set('section', chapterId)
    url.hash = anchor
    history.replaceState({}, '', url)
    requestAnimationFrame(() => document.getElementById(anchor)?.scrollIntoView({ block: 'start' }))
  }
  const followAnchor = (event) => {
    const link = event.target.closest('a[href^="#"]')
    if (!link) return
    const anchor = decodeURIComponent(link.getAttribute('href').slice(1))
    const owner = parsed.chapters.find((chapter) => chapter.id === anchor || chapter.anchors.includes(anchor))
    if (owner) { event.preventDefault(); choose(owner.id, anchor) }
  }
  const matches = useMemo(() => query ? parsed.chapters.filter((chapter) => chapter.text.toLowerCase().includes(query.toLowerCase())) : [], [parsed.chapters, query])
  const chapter = parsed.chapters.find((item) => item.id === active) || defaultChapter
  const readingIds = useMemo(() => query ? [] : [chapter?.id, ...(parsed.toc.find((item) => item.id === chapter?.id)?.children || []).map((item) => item.id)].filter(Boolean), [chapter, parsed.toc, query])
  const readingSection = useReadingSection(readingIds)
  const submitSearch = (event) => { event.preventDefault(); setQuery(draft.trim()) }

  return <main id="main" className="page reader-page report-reader">
    {report.status === 'loading' && <Status state="loading">{zh ? '正在读取报告' : 'Loading report'}</Status>}
    {report.status === 'error' && <Status state="error" onRetry={report.run}>{report.error?.message}</Status>}
    {report.status === 'success' && <>
      <div className="report-intro" dangerouslySetInnerHTML={{ __html: parsed.intro }} />
      <form className="report-search" onSubmit={submitSearch}><label><span>{zh ? '搜索完整报告' : 'Search the full report'}</span><input value={draft} onChange={(event) => setDraft(event.target.value)} placeholder={zh ? '输入关键词，例如：基线、参数、稳健性' : 'Enter a keyword, e.g. baseline, parameter, robustness'} /></label><div><button type="submit">{zh ? '搜索' : 'Search'}</button><button type="button" onClick={() => { setDraft(''); setQuery('') }}>{zh ? '清除搜索' : 'Clear search'}</button></div></form>
      {query ? <section className="report-search-results"><p>{zh ? `找到 ${matches.length} 个匹配章节` : `${matches.length} matching sections`}</p>{matches.map((item) => <button key={item.id} onClick={() => choose(item.id)}><strong>{item.title}</strong><span>{snippet(item.text, query)}</span></button>)}{!matches.length && <Status>{zh ? '没有找到匹配章节，请尝试其他关键词。' : 'No matching section was found. Try another keyword.'}</Status>}</section> : <>
        <nav className="report-directory" aria-label={zh ? '目录' : 'Contents'}><h2>{zh ? '目录' : 'Contents'}</h2><ol>{parsed.toc.map((item) => <li key={item.id}><div><button className="toc-toggle" aria-label={zh ? `展开“${item.title}”子目录` : `Open subsections for ${item.title}`} aria-expanded={expanded === item.id} onClick={() => setExpanded(expanded === item.id ? null : item.id)}><ChevronRight size={18} aria-hidden="true" /></button><button onClick={() => choose(item.id)}>{item.title}</button></div>{expanded === item.id && item.children.length > 0 && <ul>{item.children.map((child) => <li key={child.id}><button onClick={() => choose(item.id, child.id)}>{child.title}</button></li>)}</ul>}</li>)}</ol></nav>
        <div className="reader-layout"><article tabIndex="-1" className="reader-document report-document" onClick={followAnchor} dangerouslySetInnerHTML={{ __html: chapter?.html || '' }} />
          <aside className="reader-rail"><span>{zh ? '本页目录' : 'On this page'}</span><nav>{parsed.toc.map((item) => <div key={item.id}><button className={readingSection === item.id ? 'active' : ''} aria-current={readingSection === item.id ? 'location' : undefined} onClick={() => choose(item.id)}>{item.title}</button>{chapter?.id === item.id && item.children.map((child) => <button className={`sub${readingSection === child.id ? ' active' : ''}`} aria-current={readingSection === child.id ? 'location' : undefined} key={child.id} onClick={() => choose(item.id, child.id)}>{child.title}</button>)}</div>)}</nav></aside>
        </div>
      </>}
    </>}
  </main>
}
