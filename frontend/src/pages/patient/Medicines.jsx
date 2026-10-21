import { useState } from 'react'
import { api, useApi } from '../../api'
import { useSession } from '../../session'
import { DAYS, addDays, dayOf, dayNum, hhmm, todayYmd, weekdayShort } from '../../format'
import { Empty, ErrorBox, Loading, PageHead } from '../../components/ui'
import DoseStrip from '../../components/DoseStrip'

const dnum = (s) => Math.round(new Date(s + 'T00:00:00Z') / 864e5)

function Timeline({ meds }) {
  const today = todayYmd()
  const from = dnum(addDays(today, -60)), to = dnum(addDays(today, 45))
  const W = 900, LBL = 190, ROW = 34, T = 26
  const H = T + meds.length * ROW + 8
  const x = (d) => LBL + ((Math.min(Math.max(d, from), to) - from) / (to - from)) * (W - LBL - 8)
  const span = (m) => [dnum(m.start_date), m.end_date ? dnum(m.end_date) : Infinity]

  // where does each medicine overlap any other?
  const overlaps = meds.map((m, i) => {
    const [a0, a1] = span(m)
    return meds.flatMap((o, j) => {
      if (i === j) return []
      const [b0, b1] = span(o)
      const s = Math.max(a0, b0), e = Math.min(a1, b1)
      return s < e ? [[s, e]] : []
    })
  })
  const months = []
  for (let d = from; d <= to; d++) {
    const ds = new Date(d * 864e5).toISOString().slice(0, 10)
    if (ds.endsWith('-01')) months.push([d, new Date(ds).toLocaleString('en-IN', { month: 'short' })])
  }

  return (
    <svg className="gantt" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Medicine timeline with overlapping periods hatched">
      <defs>
        <pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <rect width="3" height="6" fill="#e9a93a" />
        </pattern>
        <linearGradient id="ongoing" x1="0" x2="1">
          <stop offset="0.75" stopColor="#7b1e3a" /><stop offset="1" stopColor="#7b1e3a" stopOpacity="0.15" />
        </linearGradient>
      </defs>
      {months.map(([d, label]) => (
        <g key={d}>
          <line x1={x(d)} x2={x(d)} y1={T - 6} y2={H} stroke="#f3e5c6" />
          <text x={x(d) + 4} y={T - 10} style={{ font: '12px var(--body)', fill: '#8e7a7f' }}>{label}</text>
        </g>
      ))}
      <line x1={x(dnum(today))} x2={x(dnum(today))} y1={T - 18} y2={H} stroke="#2b1a20" strokeWidth="1.5" />
      <text x={x(dnum(today))} y={T - 10} textAnchor="middle" style={{ font: '700 12px var(--body)', fill: '#2b1a20' }} dx="18">Today</text>
      {meds.map((m, i) => {
        const [s, e] = span(m)
        const y = T + i * ROW + 6
        const x0 = x(s), x1 = x(e === Infinity ? to : e)
        return (
          <g key={m.medication_id}>
            <text x={0} y={y + 15} style={{ font: '14px var(--body)', fill: '#2b1a20' }}>{m.drug_name.length > 24 ? m.drug_name.slice(0, 23) + '…' : m.drug_name}</text>
            {x1 > x0 && <rect x={x0} y={y} width={x1 - x0} height="20" rx="10" fill={e === Infinity ? 'url(#ongoing)' : m.is_active_today ? '#7b1e3a' : '#d4a7b4'} />}
            {overlaps[i].map(([os, oe], k) => {
              const ox0 = x(os), ox1 = x(oe === Infinity ? to : oe)
              return ox1 > ox0 ? <rect key={k} x={ox0} y={y + 14} width={ox1 - ox0} height="6" fill="url(#hatch)" /> : null
            })}
          </g>
        )
      })}
    </svg>
  )
}

function Adherence({ patientId }) {
  const { data } = useApi(`/patients/${patientId}/adherence`)
  if (!data) return null
  if (!data.length) return <p className="muted">No dose history yet.</p>
  const avg = data.reduce((s, d) => s + Number(d.adherence_pct), 0) / data.length
  const shade = (p) => (p >= 100 ? '#7b1e3a' : p >= 75 ? '#a8435f' : p >= 50 ? '#dfa5b5' : p > 0 ? '#f3d98a' : '#f0b8b0')
  return (
    <div className="stack">
      <p><span className="bigstat num" style={{ fontSize: 28 }}>{Math.round(avg)}%</span> <span className="muted">of doses taken over the last {data.length} days</span></p>
      <div className="row" style={{ gap: 4 }}>
        {data.map((d) => (
          <div key={d.reminder_date} title={`${dayOf(d.reminder_date)}: ${d.doses_taken} of ${d.doses_scheduled} taken`}
               style={{ width: 22, height: 22, borderRadius: 5, background: shade(Number(d.adherence_pct)) }} />
        ))}
      </div>
      <p className="faint small">Each square is a day: dark green means every dose taken, red means none.</p>
    </div>
  )
}

function AddMedicine({ patientId, onAdded }) {
  const today = todayYmd()
  const blank = { drug_name: '', dosage: '', start_date: today, end_date: addDays(today, 7), ongoing: false, times: [{ t: '08:00', days: [0, 1, 2, 3, 4, 5, 6] }] }
  const [f, setF] = useState(blank)
  const [err, setErr] = useState(null)
  const [overlaps, setOverlaps] = useState(null)
  const set = (p) => setF((s) => ({ ...s, ...p }))
  const setTime = (i, p) => set({ times: f.times.map((t, j) => (i === j ? { ...t, ...p } : t)) })

  const submit = async (e) => {
    e.preventDefault()
    setErr(null)
    try {
      const res = await api(`/patients/${patientId}/medications`, {
        method: 'POST',
        body: {
          drug_name: f.drug_name, dosage: f.dosage, start_date: f.start_date, end_date: f.ongoing ? null : f.end_date,
          reminders: f.times.map((t) => ({ reminder_time: t.t, days_of_week: t.days })),
        },
      })
      setOverlaps(res.overlaps.map((o) => (o.drug_a === res.drug_name ? o.drug_b : o.drug_a)))
      setF(blank)
      onAdded()
    } catch (e2) { setErr(e2) }
  }

  return (
    <form className="panel stack" onSubmit={submit}>
      <h2>Add a medicine</h2>
      <div className="row top">
        <label className="field grow"><span>Medicine and strength</span>
          <input required value={f.drug_name} onChange={(e) => set({ drug_name: e.target.value })} placeholder="Amoxicillin 500mg" /></label>
        <label className="field grow"><span>How to take it</span>
          <input required value={f.dosage} onChange={(e) => set({ dosage: e.target.value })} placeholder="1 capsule after food" /></label>
      </div>
      <div className="row top">
        <label className="field"><span>From</span><input type="date" required value={f.start_date} onChange={(e) => set({ start_date: e.target.value })} /></label>
        <label className="field"><span>Last day is the day before</span>
          <input type="date" disabled={f.ongoing} value={f.end_date} min={addDays(f.start_date, 1)} onChange={(e) => set({ end_date: e.target.value })} /></label>
        <label className="row small" style={{ alignSelf: 'end', paddingBottom: 9, gap: 8 }}>
          <input type="checkbox" checked={f.ongoing} onChange={(e) => set({ ongoing: e.target.checked })} /> No end date
        </label>
      </div>
      <div className="stack">
        <span className="small muted">Reminder times</span>
        {f.times.map((t, i) => (
          <div key={i} className="row">
            <input type="time" value={t.t} required onChange={(e) => setTime(i, { t: e.target.value })} style={{ width: 130 }} />
            <div className="dayboxes">
              {DAYS.map((d, dw) => {
                const on = t.days.includes(dw)
                return (
                  <label key={d} className={on ? 'on' : ''}>
                    <input type="checkbox" checked={on} onChange={() => setTime(i, { days: on ? t.days.filter((x) => x !== dw) : [...t.days, dw].sort() })} />
                    {d.slice(0, 2)}
                  </label>
                )
              })}
            </div>
            {f.times.length > 1 && <button type="button" className="btn ghost sm" onClick={() => set({ times: f.times.filter((_, j) => j !== i) })}>Remove</button>}
          </div>
        ))}
        <div><button type="button" className="btn ghost sm" onClick={() => set({ times: [...f.times, { t: '20:00', days: [0, 1, 2, 3, 4, 5, 6] }] })}>Add another time</button></div>
      </div>
      <div className="row"><button className="btn">Add medicine</button></div>
      <ErrorBox error={err} />
      {overlaps && (overlaps.length
        ? <div className="notice">Added. Its dates overlap with <b>{overlaps.join(', ')}</b>. That’s a schedule check, not medical advice.</div>
        : <div className="notice ok">Added. No date overlaps with other medicines.</div>)}
    </form>
  )
}

export default function Medicines() {
  const { patientId } = useSession()
  const meds = useApi(`/patients/${patientId}/medications`)
  const overlaps = useApi(`/patients/${patientId}/medications/overlaps`, { active_on: todayYmd() }, [meds.data])
  const [err, setErr] = useState(null)
  const today = todayYmd()

  const stop = async (m) => {
    setErr(null)
    try { await api(`/medications/${m.medication_id}`, { method: 'PATCH', body: { end_date: addDays(today, 1) } }); meds.reload() } catch (e) { setErr(e) }
  }

  const list = (meds.data || []).slice().sort((a, b) => (a.start_date < b.start_date ? -1 : 1))
  const shown = list.filter((m) => !m.end_date || m.end_date >= addDays(today, -60))

  return (
    <div className="page stack lg">
      <PageHead title="Medicines">
        Your prescriptions on one timeline. Yellow hatching marks the days two medicines run at the same time.
      </PageHead>

      <section>
        <h2 style={{ marginBottom: 12 }}>Today, {weekdayShort(today)} {dayNum(today)}</h2>
        <DoseStrip patientId={patientId} />
      </section>

      <section>
        <h2 style={{ marginBottom: 12 }}>Timeline</h2>
        {meds.loading && !meds.data ? <Loading /> : shown.length ? <Timeline meds={shown} /> : <Empty>No medicines recorded. Add one below.</Empty>}
        {overlaps.data?.length > 0 && (
          <div className="notice" style={{ marginTop: 14 }}>
            <b>Overlapping today:</b>{' '}
            {overlaps.data.map((o) => `${o.drug_a} with ${o.drug_b}`).join('; ')}.
            <div className="small">Found with the date-range overlap operator. This is a scheduling signal, not advice about combining medicines.</div>
          </div>
        )}
      </section>

      <div className="two-col">
        <section>
          <h2 style={{ marginBottom: 8 }}>All prescriptions</h2>
          <ErrorBox error={err || meds.error} />
          <table className="ledger">
            <thead><tr><th>Medicine</th><th>Dates</th><th>Reminders</th><th /></tr></thead>
            <tbody>
              {list.map((m) => (
                <tr key={m.medication_id} style={{ opacity: m.is_active_today ? 1 : 0.6 }}>
                  <td><b>{m.drug_name}</b><div className="muted small">{m.dosage}</div></td>
                  <td className="small">{dayOf(m.start_date)}<br />{m.end_date ? `until ${dayOf(addDays(m.end_date, -1))}` : 'ongoing'}</td>
                  <td className="small">{m.reminders.map((r) => (
                    <div key={r.medication_reminder_id}>{hhmm(r.reminder_time)}{r.days_of_week.length < 7 ? `, ${r.days_of_week.map((d) => DAYS[d]).join('/')}` : ''}</div>
                  ))}</td>
                  <td className="r">{m.is_active_today && <button className="btn ghost sm" onClick={() => stop(m)}>Stop after today</button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
        <div className="stack lg">
          <section className="panel tint"><h2 style={{ marginBottom: 12 }}>Last 30 days</h2><Adherence patientId={patientId} /></section>
          <AddMedicine patientId={patientId} onAdded={meds.reload} />
        </div>
      </div>
    </div>
  )
}
