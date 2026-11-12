import { useEffect, useId, useRef, useState } from 'react'
import { api } from '../api/client'
import './stock-search.css'

export function StockSearch({ zh, market, query, onQueryChange, onSelect, disabled = false, isSelected = () => false }) {
  const id = useId()
  const root = useRef(null)
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(-1)
  const [placement, setPlacement] = useState({})
  const [search, setSearch] = useState({ status: 'idle', items: [], key: '' })
  const term = query.trim()
  const key = `${market}:${term}`
  const items = search.key === key ? search.items : []
  const expanded = open && Boolean(term) && !disabled

  useEffect(() => {
    let cancelled = false
    setActive(-1)
    if (!term) { setSearch({ status: 'idle', items: [], key }); return }
    setSearch({ status: 'loading', items: [], key })
    const timer = setTimeout(() => {
      api.stocks(market, term).then(data => {
        if (!cancelled) setSearch({ status: 'success', items: (data.items || []).slice(0, 8), key })
      }).catch(error => {
        if (!cancelled) setSearch({ status: 'error', items: [], key, error: error.message })
      })
    }, 260)
    return () => { cancelled = true; clearTimeout(timer) }
  }, [market, term])

  useEffect(() => {
    const dismiss = event => { if (!root.current?.contains(event.target)) setOpen(false) }
    document.addEventListener('pointerdown', dismiss)
    return () => document.removeEventListener('pointerdown', dismiss)
  }, [])

  useEffect(() => {
    if (!expanded) return
    const position = () => {
      const rect = root.current?.getBoundingClientRect()
      if (!rect) return
      const below = window.innerHeight - rect.bottom - 12
      const above = rect.top - 12
      const up = below < 220 && above > below
      setPlacement({ top: up ? 'auto' : '100%', bottom: up ? '100%' : 'auto', marginTop: up ? 0 : 6, marginBottom: up ? 6 : 0, maxHeight: Math.max(100, Math.min(320, up ? above : below)) })
    }
    position()
    window.addEventListener('resize', position)
    window.addEventListener('scroll', position, true)
    return () => { window.removeEventListener('resize', position); window.removeEventListener('scroll', position, true) }
  }, [expanded])

  const choose = item => {
    if (disabled || isSelected(item)) return
    setOpen(false); setActive(-1); onSelect(item)
  }
  const navigate = event => {
    if (event.key === 'Escape') { setOpen(false); setActive(-1); return }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault(); setOpen(true)
      const choices = items.map((item, index) => isSelected(item) ? -1 : index).filter(index => index >= 0)
      if (!choices.length) return
      const current = choices.indexOf(active)
      const next = event.key === 'ArrowDown' ? (current + 1) % choices.length : (current <= 0 ? choices.length - 1 : current - 1)
      setActive(choices[next])
      root.current?.querySelectorAll('[role="option"]')[choices[next]]?.scrollIntoView({ block: 'nearest' })
    } else if (event.key === 'Enter' && expanded && active >= 0 && items[active]) {
      event.preventDefault(); choose(items[active])
    }
  }

  return <div className="stock-search" ref={root} onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false) }}>
    <label className="field" htmlFor={id}>{zh ? '股票代码或名称' : 'Stock symbol or name'}</label>
    <input id={id} role="combobox" autoComplete="off" aria-autocomplete="list" aria-expanded={expanded} aria-controls={`${id}-results`} aria-activedescendant={expanded && active >= 0 ? `${id}-${active}` : undefined}
      disabled={disabled} value={query} placeholder={zh ? '例如 AAPL / 苹果 / 600519' : 'e.g. AAPL / Apple / 600519'}
      onFocus={() => setOpen(true)} onChange={event => { onQueryChange(event.target.value); setOpen(true); setActive(-1) }} onKeyDown={navigate}/>
    {expanded && <div className="stock-search-popover" style={placement}>
      {(search.key !== key || search.status === 'loading') && <p role="status">{zh ? '正在搜索…' : 'Searching…'}</p>}
      {search.key === key && search.status === 'error' && <p role="alert">{search.error}</p>}
      {search.key === key && search.status === 'success' && !items.length && <p role="status">{zh ? '未找到匹配股票' : 'No matching stocks'}</p>}
      <div id={`${id}-results`} role="listbox" aria-label={zh ? '搜索结果' : 'Search results'}>
        {items.map((item, index) => <button type="button" role="option" id={`${id}-${index}`} key={item.symbol} aria-selected={active === index} disabled={isSelected(item)} onMouseDown={event => event.preventDefault()} onClick={() => choose(item)}>
          <span><strong>{item.symbol}</strong><small>{item.name}</small></span><span>{isSelected(item) ? (zh ? '已选' : 'Selected') : (zh ? '选择' : 'Select')}</span>
        </button>)}
      </div>
    </div>}
  </div>
}
