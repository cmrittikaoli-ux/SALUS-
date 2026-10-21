import { useEffect, useState } from 'react'
import { api, useApi } from '../api'
import { useSession } from '../session'
import { addDays, dateTime, relative, time, todayYmd } from '../format'
import { ErrorBox, PageHead } from '../components/ui'

const shuffle = (a) => a.map((v) => [Math.random(), v]).sort((x, y) => x[0] - y[0]).map((x) => x[1])

async function firstFreeSlot(doctorId) {
  const from = addDays(todayYmd(), 1)
  const days = await api(`/doctors/${doctorId}/slots`, { params: { date: from, days: 7 } })
  for (const d of Object.keys(days).sort()) if (days[d].length) return days[d][0]
  return null
}

// a free slot whose following slot is free too, so an offset start overlaps nothing booked
async function freeRun(doctorId) {
  const days = await api(`/doctors/${doctorId}/slots`, { params: { date: addDays(todayYmd(), 1), days: 7 } })
  for (const d of Object.keys(days).sort()) {
    const s = days[d]
    for (let i = 0; i + 1 < s.length; i++) if (s[i].slot_end === s[i + 1].slot_start) return s[i]
  }
  return null
}

function Race({ doctors, patients }) {
  const withHours = doctors
  const [doctorId, setDoctorId] = useState(doctors[0]?.doctor_id)
  const [slot, setSlot] = useState(null)
  const [results, setResults] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  useEffect(() => {
    let live = true
    setSlot(null); setResults(null)
    firstFreeSlot(doctorId).then((s) => live && setSlot(s)).catch((e) => live && setErr(e))
    return () => { live = false }
  }, [doctorId])

  const run = async () => {
    setBusy(true); setErr(null); setResults(null)
    const racers = shuffle(patients).slice(0, 20)
    const t0 = performance.now()
    const out = await Promise.all(racers.map((p) =>
      api('/appointments', { method: 'POST', body: { patient_id: p.patient_id, doctor_id: doctorId, start_at: slot.slot_start } })
        .then((a) => ({ ok: true, who: p.full_name, a }))
        .catch((e) => ({ ok: false, who: p.full_name, e }))))
    setResults({ out, ms: Math.round(performance.now() - t0) })
    setBusy(false)
    firstFreeSlot(doctorId).then(setSlot)
  }

  const wins = results?.out.filter((r) => r.ok) || []
  const conflicts = results?.out.filter((r) => !r.ok && r.e.status === 409) || []
  const other = results?.out.filter((r) => !r.ok && r.e.status !== 409) || []

  return (
    <section className="panel stack">
      <div className="panel-title"><h2>Twenty patients, one slot</h2></div>
      <p className="muted" style={{ maxWidth: '68ch' }}>
        Sends 20 booking requests for the same slot at the same moment. The booking function locks the doctor’s row
        (<code>SELECT … FOR UPDATE</code>), so the requests queue up. Only the first can win; the rest find the slot taken.
        If anything slipped past, the <code>no_double_booking</code> exclusion constraint would still refuse it.
      </p>
      <div className="row">
        <label className="field"><span>Doctor</span>
          <select value={doctorId} onChange={(e) => setDoctorId(e.target.value)} style={{ maxWidth: 320 }}>
            {withHours.map((d) => <option key={d.doctor_id} value={d.doctor_id}>Dr {d.full_name}, {d.specialty}</option>)}
          </select>
        </label>
        <div className="field"><span>Slot everyone wants</span>
          <b style={{ minHeight: 40, display: 'flex', alignItems: 'center' }}>{slot ? dateTime(slot.slot_start) : 'Finding a free slot…'}</b>
        </div>
        <button className="btn" style={{ alignSelf: 'end' }} disabled={!slot || busy} onClick={run}>{busy ? 'Racing…' : 'Send 20 bookings at once'}</button>
      </div>
      <ErrorBox error={err} />
      <div className="race" aria-live="polite">
        {(results?.out || Array.from({ length: 20 })).map((r, i) => (
          <i key={i} className={r ? (r.ok ? 'win' : 'lose') : ''} style={{ animationDelay: `${i * 25}ms` }} title={r?.who}>
            {r ? (r.ok ? '✓' : r.e.status) : ''}
          </i>
        ))}
      </div>
      {results && (
        <div className="row" style={{ gap: 24, alignItems: 'center' }}>
          <span className={`stamp fresh ${wins.length === 1 ? '' : 'blocked'}`}>{wins.length} booked</span>
          <div>
            <p><b>{wins[0]?.who || 'Nobody'}</b> got the slot. {conflicts.length} request{conflicts.length === 1 ? ' was' : 's were'} refused with 409
              {other.length ? `, ${other.length} for another reason (that patient was already booked elsewhere then)` : ''}. Took {results.ms} ms.</p>
            {conflicts[0] && <p className="muted small">Database said: “{conflicts[0].e.message}”</p>}
          </div>
        </div>
      )}
    </section>
  )
}

function useRules(doctors, patients) {
  const doc = doctors[0]
  const today = todayYmd()
  return [
    {
      name: 'Book a slot in the past', by: 'trg_validate_appointment',
      run: async () => {
        // a real working slot ~200 days ago, long before any seeded booking
        const [b] = await api(`/doctors/${doc.doctor_id}/schedule`)
        let d = addDays(today, -200)
        while (new Date(d + 'T12:00:00+05:30').getDay() !== b.day_of_week) d = addDays(d, -1)
        return api('/appointments', { method: 'POST', body: { patient_id: patients[0].patient_id, doctor_id: doc.doctor_id, start_at: `${d}T${b.start_time.slice(0, 5)}:00+05:30` } })
      },
    },
    {
      name: 'Book at 5 AM, outside clinic hours', by: 'fn_book_appointment',
      run: async () => api('/appointments', { method: 'POST', body: { patient_id: patients[0].patient_id, doctor_id: doc.doctor_id, start_at: `${addDays(today, 1)}T05:00:00+05:30` } }),
    },
    {
      name: 'Book 7 minutes into a slot', by: 'trg_validate_appointment',
      run: async () => {
        const s = await freeRun(doc.doctor_id)
        const start = new Date(new Date(s.slot_start).getTime() + 7 * 60000).toISOString()
        return api('/appointments', { method: 'POST', body: { patient_id: patients[1].patient_id, doctor_id: doc.doctor_id, start_at: start } })
      },
    },
    {
      name: 'Review a visit that hasn’t happened', by: 'trg_validate_review',
      run: async () => {
        const [a] = await api('/appointments', { params: { status: 'scheduled', limit: 1 } })
        return api('/reviews', { method: 'POST', body: { appointment_id: a.appointment_id, patient_id: a.patient_id, rating: 5 } })
      },
    },
    {
      name: 'Review someone else’s visit', by: 'trg_validate_review',
      run: async () => {
        const list = await api('/appointments', { params: { status: 'completed', limit: 200 } })
        const a = list.find((x) => !x.has_review)
        const stranger = patients.find((p) => p.patient_id !== a.patient_id)
        return api('/reviews', { method: 'POST', body: { appointment_id: a.appointment_id, patient_id: stranger.patient_id, rating: 1 } })
      },
    },
    {
      name: 'Review the same visit twice', by: 'reviews_appointment_id_key',
      run: async () => {
        const list = await api('/appointments', { params: { status: 'completed', limit: 200 } })
        const a = list.find((x) => x.has_review)
        return api('/reviews', { method: 'POST', body: { appointment_id: a.appointment_id, patient_id: a.patient_id, rating: 4 } })
      },
    },
    {
      name: 'Mark next week’s visit as completed', by: 'trg_validate_status_change',
      run: async () => {
        const list = await api('/appointments', { params: { status: 'scheduled', from: new Date(Date.now() + 2 * 864e5).toISOString(), limit: 1 } })
        return api(`/appointments/${list[0].appointment_id}/complete`, { method: 'POST' })
      },
    },
    {
      name: 'Give a doctor two overlapping shifts', by: 'no_overlapping_blocks',
      run: async () => {
        const blocks = await api(`/doctors/${doc.doctor_id}/schedule`)
        const b = blocks[0]
        const [h, m] = b.start_time.split(':').map(Number)
        const shifted = `${String(h + 1).padStart(2, '0')}:${String(m).padStart(2, '0')}`
        return api(`/doctors/${doc.doctor_id}/schedule`, { method: 'PUT', body: [...blocks, { ...b, start_time: shifted, end_time: b.end_time }] })
      },
    },
  ]
}

function Rules({ doctors, patients }) {
  const rules = useRules(doctors, patients)
  const [out, setOut] = useState({})
  const run = async (r) => {
    setOut((o) => ({ ...o, [r.name]: { busy: true } }))
    try {
      await r.run()
      setOut((o) => ({ ...o, [r.name]: { allowed: true } }))
    } catch (e) {
      setOut((o) => ({ ...o, [r.name]: { e } }))
    }
  }
  const runAll = async () => { for (const r of rules) await run(r) }

  return (
    <section className="panel">
      <div className="panel-title">
        <h2>Try to break the rules</h2>
        <button className="btn ghost sm" onClick={runAll}>Run all</button>
      </div>
      <p className="muted" style={{ maxWidth: '68ch' }}>Each button sends a request the database should refuse. Nothing here changes data: refused writes are rolled back.</p>
      <div className="ruled" style={{ marginTop: 8 }}>
        {rules.map((r) => {
          const o = out[r.name]
          return (
            <div key={r.name} className="rule">
              <div><b>{r.name}</b><div className="faint small">Expected to be refused by <code>{r.by}</code></div></div>
              <button className="btn ghost sm" onClick={() => run(r)} disabled={o?.busy}>{o?.busy ? 'Trying…' : 'Try it'}</button>
              {o?.e && (
                <div className="out row" style={{ gap: 14 }}>
                  <span className="stamp blocked fresh" style={{ fontSize: 16 }}>Blocked {o.e.status}</span>
                  <span>{o.e.message}{o.e.constraint && <span className="faint"> ({o.e.constraint})</span>}</span>
                </div>
              )}
              {o?.allowed && <div className="out notice alarm">This went through, so the rule is not being enforced.</div>}
            </div>
          )
        })}
      </div>
    </section>
  )
}

function ReminderDesk() {
  const [tick, setTick] = useState(0)
  const feed = useApi('/admin/notifications', { limit: 30 }, [tick])
  const pending = useApi('/reminders/pending', { within_hours: 3 }, [tick])
  const jobs = useApi('/admin/jobs', null, [tick])
  const [dispatch, setDispatch] = useState(null)
  const [err, setErr] = useState(null)

  useEffect(() => { const t = setInterval(() => setTick((n) => n + 1), 10000); return () => clearInterval(t) }, [])
  const sendNow = async () => {
    setErr(null)
    try { setDispatch(await api('/admin/dispatch', { method: 'POST' })); setTick((n) => n + 1) } catch (e) { setErr(e) }
  }

  return (
    <div className="two-col">
      <section className="panel">
        <div className="panel-title">
          <h2>Reminders going out</h2>
          <button className="btn ghost sm" onClick={sendNow}>Send due reminders now</button>
        </div>
        <p className="muted small" style={{ marginBottom: 10 }}>
          pg_cron runs the dispatcher every minute. Each reminder it sends raises a <code>NOTIFY</code>, which the API hears
          and lists here (this is where email or SMS would plug in). Refreshes every 10 seconds.
        </p>
        <ErrorBox error={err} />
        {dispatch && <div className="notice ok small" style={{ marginBottom: 10 }}>
          Just now: {dispatch.appointment_reminders_sent} appointment and {dispatch.medication_reminders_sent} dose reminder(s) sent.
        </div>}
        <div className="feed ruled">
          {(feed.data || []).length === 0 && <p className="faint">Nothing delivered since the API started. Reminders appear here as they fall due.</p>}
          {(feed.data || []).map((n, i) => (
            <div key={i}>
              <span className={`chip k ${n.kind === 'appointment' ? 'scheduled' : 'sticker'}`}>{n.kind === 'appointment' ? 'Visit' : 'Dose'}</span>
              <span>
                <b>{n.patient}</b>{' '}
                {n.kind === 'appointment' ? `has Dr ${n.doctor} at ${dateTime(n.starts_at)}` : `should take ${n.drug} (${n.dosage})`}
              </span>
            </div>
          ))}
        </div>
      </section>

      <div className="stack lg">
        <section>
          <h2 style={{ marginBottom: 8 }}>Due in the next 3 hours</h2>
          <table className="ledger small">
            <tbody>
              {(pending.data || []).slice(0, 8).map((r) => (
                <tr key={r.reminder_id}><td className="num">{time(r.remind_at)}</td><td>{r.patient_name}</td><td className="faint">{relative(r.remind_at)}</td></tr>
              ))}
              {pending.data && !pending.data.length && <tr><td className="faint">None due.</td></tr>}
            </tbody>
          </table>
          {pending.data?.length > 8 && <p className="faint small">and {pending.data.length - 8} more</p>}
        </section>
        <section>
          <h2 style={{ marginBottom: 8 }}>Scheduled jobs</h2>
          {jobs.data && !jobs.data.pg_cron && <p className="muted">pg_cron isn’t installed, so the API runs these jobs itself every minute.</p>}
          {jobs.data?.pg_cron && (
            <table className="ledger small">
              <thead><tr><th>Job</th><th>Runs</th><th className="r">Last result</th></tr></thead>
              <tbody>
                {jobs.data.jobs.map((j) => {
                  const lastRun = jobs.data.recent_runs.find((r) => r.jobid === j.jobid && r.start_time)
                  return (
                    <tr key={j.jobid}>
                      <td>{j.jobname.replace('salus_', '').replaceAll('_', ' ')}</td>
                      <td><code>{j.schedule}</code></td>
                      <td className="r">{lastRun ? <span className={`chip ${lastRun.status === 'succeeded' ? 'completed' : 'alarm'}`}>{lastRun.status}, {time(lastRun.start_time)}</span> : <span className="faint">not yet</span>}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </section>
      </div>
    </div>
  )
}

export default function UnderTheHood() {
  const { doctors, patients } = useSession()
  const stats = useApi('/admin/stats')
  const s = stats.data

  return (
    <div className="page stack lg">
      <PageHead title="Under the hood">
        The rules behind Salus live in PostgreSQL, not in this page. Use these controls to watch the database enforce them.
      </PageHead>

      {s && (
        <div className="row" style={{ gap: 36 }}>
          {[['patients', s.patients], ['doctors', s.doctors], ['appointments', s.appointments], ['upcoming', s.upcoming_appointments],
            ['reviews', s.reviews], ['active prescriptions', s.active_medications], ['overlapping today', s.overlapping_pairs_today]].map(([k, v]) => (
            <div key={k}><div className="bigstat num">{Number(v).toLocaleString('en-IN')}</div><span className="muted small">{k}</span></div>
          ))}
        </div>
      )}

      <Race doctors={doctors} patients={patients} />
      <Rules doctors={doctors} patients={patients} />
      <ReminderDesk />
    </div>
  )
}
