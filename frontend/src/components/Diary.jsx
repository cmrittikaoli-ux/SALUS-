import { useState } from 'react'
import { api, useApi } from '../api'
import { dayOf, time, todayYmd } from '../format'
import { Empty, ErrorBox, Loading } from './ui'

function Entry({ e, onChanged }) {
  const [editing, setEditing] = useState(false)
  const [text, setText] = useState(e.body)
  const [err, setErr] = useState(null)

  const save = async () => {
    setErr(null)
    try { await api(`/diary/${e.entry_id}`, { method: 'PATCH', body: { body: text } }); setEditing(false); onChanged() } catch (x) { setErr(x) }
  }
  const remove = async () => {
    if (!window.confirm('Delete this diary note?')) return
    try { await api(`/diary/${e.entry_id}`, { method: 'DELETE' }); onChanged() } catch (x) { setErr(x) }
  }

  return (
    <div className="diary-entry">
      <span className="faint small num">{time(e.created_at)}</span>
      {editing ? (
        <div className="stack" style={{ gap: 8 }}>
          <textarea rows={3} maxLength={2000} value={text} onChange={(x) => setText(x.target.value)} />
          <div className="row" style={{ gap: 6 }}>
            <button className="btn sm" disabled={!text.trim()} onClick={save}>Save</button>
            <button className="btn ghost sm" onClick={() => { setEditing(false); setText(e.body) }}>Cancel</button>
          </div>
        </div>
      ) : (
        <p>{e.body}</p>
      )}
      {!editing && (
        <div className="diary-acts">
          <button onClick={() => setEditing(true)}>Edit</button>
          <button onClick={remove}>Delete</button>
        </div>
      )}
      <ErrorBox error={err} />
    </div>
  )
}

/** A private notebook for everyday things. `todayOnly` keeps it small for the home screen. */
export default function Diary({ patientId, todayOnly = false }) {
  const today = todayYmd()
  const { data, error, loading, reload } = useApi(`/patients/${patientId}/diary`, todayOnly ? { from: today, to: today } : {})
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  const add = async (ev) => {
    ev.preventDefault()
    setBusy(true); setErr(null)
    try { await api(`/patients/${patientId}/diary`, { method: 'POST', body: { body: text } }); setText(''); reload() } catch (x) { setErr(x) }
    setBusy(false)
  }

  const byDay = []
  for (const e of data || []) {
    const last = byDay[byDay.length - 1]
    if (last && last[0] === e.entry_date) last[1].push(e)
    else byDay.push([e.entry_date, [e]])
  }

  return (
    <div className="stack">
      <form className="stack" style={{ gap: 8 }} onSubmit={add}>
        <textarea rows={todayOnly ? 2 : 3} maxLength={2000} placeholder="What happened today? Errands, a walk, what you had for tea…"
                  value={text} onChange={(e) => setText(e.target.value)} aria-label="New diary note" />
        <div className="row" style={{ justifyContent: 'space-between' }}>
          <span className="faint small">Only you can read your diary.</span>
          <button className="btn sm" disabled={busy || !text.trim()}>{busy ? 'Saving…' : 'Add note'}</button>
        </div>
      </form>
      <ErrorBox error={error || err} />
      {loading && !data ? <Loading what="Opening your diary" />
        : !byDay.length ? (todayOnly ? <p className="faint small">Nothing written today yet.</p> : <Empty>No notes in the last 30 days.</Empty>)
          : byDay.map(([d, entries]) => (
            <div key={d}>
              {!todayOnly && <h3 className="diary-day">{d === today ? 'Today' : dayOf(d)}</h3>}
              <div className="ruled">{entries.map((e) => <Entry key={e.entry_id} e={e} onChanged={reload} />)}</div>
            </div>
          ))}
    </div>
  )
}
