import { AlertCircle, ArrowUpRight, LoaderCircle } from 'lucide-react'

export function PageIntro({ index, eyebrow, title, text, aside }) {
  return <section className="page-intro">
    <div className="section-index">{index}</div>
    <div><p className="eyebrow">{eyebrow}</p><h1>{title}<span className="blue-dot">.</span></h1><p className="lede">{text}</p></div>
    {aside && <div className="intro-aside">{aside}</div>}
  </section>
}

export function Section({ index, title, description, children, className = '' }) {
  return <section className={`numbered-section ${className}`}>
    <div className="section-index">{index}</div>
    <div className="section-heading"><h2>{title}</h2>{description && <p>{description}</p>}</div>
    <div className="section-body">{children}</div>
  </section>
}

export function Button({ children, className = '', variant = 'primary', ...props }) {
  return <button className={`button button-${variant} ${className}`} {...props}>{children}</button>
}

export function Status({ state = 'empty', children, onRetry }) {
  return <div className={`status status-${state}`} role={state === 'error' ? 'alert' : 'status'}>
    {state === 'loading' ? <LoaderCircle className="spin" size={18} /> : state === 'error' ? <AlertCircle size={18} /> : null}
    <span>{children}</span>{onRetry && <button onClick={onRetry}>Retry <ArrowUpRight size={14} /></button>}
  </div>
}

export function Metric({ label, value, detail }) {
  return <div className="metric"><span>{label}</span><strong>{value ?? 'N/A'}</strong>{detail && <small>{detail}</small>}</div>
}

export function Field({ label, hint, children }) {
  return <label className="field"><span>{label}</span>{children}{hint && <small>{hint}</small>}</label>
}

export function DataTable({ columns, rows = [], empty = 'No data available' }) {
  if (!rows.length) return <Status>{empty}</Status>
  return <div className="table-scroll"><table><thead><tr>{columns.map((col) => <th key={col.key}>{col.label}</th>)}</tr></thead><tbody>
    {rows.map((row, i) => <tr key={`${row.id || row.symbol || row.date || 'row'}-${i}`}>{columns.map((col) => <td key={col.key}>{col.render ? col.render(row[col.key], row) : cellValue(row[col.key])}</td>)}</tr>)}
  </tbody></table></div>
}

function cellValue(value) { if (value == null) return 'N/A'; if (typeof value === 'number') return value.toLocaleString(undefined,{maximumFractionDigits:4}); if (typeof value === 'object') return JSON.stringify(value); return String(value) }
