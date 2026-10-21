import { useEffect } from 'react'
import { STATUS_LABEL } from '../format'
import { SQL } from '../sql'

export function Loading({ what = 'Loading' }) {
  return <div className="loading">{what}…</div>
}

export function ErrorBox({ error }) {
  if (!error) return null
  return (
    <div className="notice alarm" role="alert">
      <b>{error.status ? `${error.status}: ` : ''}</b>{error.message}
      {error.constraint && <div className="small">Refused by <code>{error.constraint}</code></div>}
    </div>
  )
}

export function Empty({ children }) {
  return <div className="empty">{children}</div>
}

export function StatusChip({ status }) {
  return <span className={`chip ${status}`}>{STATUS_LABEL[status] || status}</span>
}

export function Rating({ value, count }) {
  const v = Number(value)
  return (
    <span className="num" title={`${v.toFixed(2)} from ${count} reviews`}>
      <span style={{ color: 'var(--sticker)' }}>★</span> {count ? v.toFixed(1) : 'New'}
      {count ? <span className="faint"> ({count})</span> : null}
    </span>
  )
}

export function PageHead({ title, children, actions }) {
  return (
    <div className="page-head">
      <div>
        <h1>{title}</h1>
        {children && <p className="muted">{children}</p>}
      </div>
      {actions}
    </div>
  )
}

function highlight(sql) {
  const parts = sql.split(/(\b(?:SELECT|FROM|WHERE|JOIN|ON|AND|OR|INSERT|INTO|VALUES|UPDATE|SET|WITH|AS|ORDER BY|GROUP BY|LIMIT|EXISTS|NOT|IN|OVER|WINDOW|RANGE|BETWEEN|FOR UPDATE|FOR SHARE|SKIP LOCKED|CONSTRAINT|EXCLUDE USING|CROSS JOIN LATERAL|IF|THEN|RAISE EXCEPTION|END IF|ON CONFLICT DO NOTHING|DISTINCT|FILTER|USING)\b)/g)
  return parts.map((p, i) => (i % 2 ? <span key={i} className="kw">{p}</span> : p))
}

export function SqlDrawer({ screen, open, onOpen, onClose }) {
  const info = SQL[screen]
  useEffect(() => {
    if (!open) return
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])
  if (!info) return null
  return (
    <>
      <button className="btn sql-toggle-float" onClick={onOpen}>Show the SQL</button>
      {open && (
        <aside className="sql-drawer" aria-label="SQL behind this screen">
          <button className="close" onClick={onClose}>Close</button>
          <h2>{info.title}</h2>
          <p>{info.intro}</p>
          {info.blocks.map(([title, sql]) => (
            <section key={title}>
              <h3>{title}</h3>
              <pre>{highlight(sql)}</pre>
            </section>
          ))}
        </aside>
      )}
    </>
  )
}

export function Mark() {
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="9" fill="#7b1e3a" />
      <path d="M13 7h6v6h6v6h-6v6h-6v-6H7v-6h6z" fill="#e9a93a" />
    </svg>
  )
}

export function Initials({ name, size = 64 }) {
  const letters = (name || '').split(' ').filter(Boolean).slice(0, 2).map((w) => w[0]).join('')
  return <div className="initials" style={{ width: size, height: size, fontSize: size * 0.38 }} aria-hidden="true">{letters}</div>
}
