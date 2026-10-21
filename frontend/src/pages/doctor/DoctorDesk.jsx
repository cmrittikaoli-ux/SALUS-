import { useEffect, useState } from 'react'
import { api, useApi } from '../../api'
import { useSession } from '../../session'
import { DAYS, addDays, dateTime, dayLong, hhmm, time, todayYmd } from '../../format'
import { Empty, ErrorBox, Initials, Loading, PageHead, StatusChip } from '../../components/ui'
import DoctorProfile from '../../components/DoctorProfile'

function DayList({ doctorId }) {
  const [date, setDate] = useState(todayYmd())
  const { data, error, loading, reload } = useApi(`/doctors/${doctorId}/appointments`, { on: date })
  const [err, setErr] = useState(null)
  const act = async (a, what) => {
    setErr(null)
    try { await api(`/appointments/${a.appointment_id}/${what}`, { method: 'POST' }); reload() } catch (e) { setErr(e) }
  }
  const rows = (data || []).slice().sort((a, b) => (a.start_at < b.start_at ? -1 : 1))
  const now = new Date()

  return (
    <div className="stack">
      <div className="row">
        <button className="btn ghost sm" onClick={() => setDate(addDays(date, -1))}>Previous day</button>
        <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        <button className="btn ghost sm" onClick={() => setDate(addDays(date, 1))}>Next day</button>
        <span className="muted">{dayLong(date + 'T12:00:00+05:30')}</span>
      </div>
      <ErrorBox error={error || err} />
      {loading && !data ? <Loading /> : !rows.length ? <Empty>No appointments on this day.</Empty> : (
        <table className="ledger">
          <thead><tr><th>Time</th><th>Patient</th><th>Status</th><th className="r">Mark as</th></tr></thead>
          <tbody>
            {rows.map((a) => {
              const started = new Date(a.start_at) <= now
              return (
                <tr key={a.appointment_id} style={{ opacity: a.status === 'cancelled' ? 0.5 : 1 }}>
                  <td className="num"><b>{time(a.start_at)}</b></td>
                  <td>{a.patient_name}</td>
                  <td><StatusChip status={a.status} /></td>
                  <td className="r">
                    {a.status === 'scheduled' && (
                      <div className="row" style={{ justifyContent: 'flex-end', gap: 6 }}>
                        <button className="btn ghost sm" disabled={!started} title={started ? '' : 'Available once the appointment starts'} onClick={() => act(a, 'complete')}>Seen</button>
                        <button className="btn ghost sm" disabled={!started} onClick={() => act(a, 'no-show')}>No-show</button>
                        <button className="btn danger sm" onClick={() => act(a, 'cancel')}>Cancel</button>
                      </div>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
      <p className="faint small">“Seen” and “No-show” unlock once the slot has started; the database refuses them earlier.</p>
    </div>
  )
}

function WeeklyHours({ doctorId }) {
  const { data, error, loading, reload } = useApi(`/doctors/${doctorId}/schedule`)
  const [blocks, setBlocks] = useState([])
  const [add, setAdd] = useState({ day_of_week: 1, start_time: '10:00', end_time: '13:00', slot_minutes: 20 })
  const [err, setErr] = useState(null)
  const [saved, setSaved] = useState(false)

  useEffect(() => { if (data) setBlocks(data.map((b) => ({ ...b, start_time: b.start_time.slice(0, 5), end_time: b.end_time.slice(0, 5) }))) }, [data])
  const dirty = data && JSON.stringify(blocks) !== JSON.stringify(data.map((b) => ({ ...b, start_time: b.start_time.slice(0, 5), end_time: b.end_time.slice(0, 5) })))

  const save = async () => {
    setErr(null); setSaved(false)
    try { await api(`/doctors/${doctorId}/schedule`, { method: 'PUT', body: blocks }); setSaved(true); reload() } catch (e) { setErr(e) }
  }

  if (loading && !data) return <Loading />
  return (
    <div className="stack lg">
      <ErrorBox error={error} />
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, minmax(110px, 1fr))', gap: 8, overflowX: 'auto' }}>
        {[1, 2, 3, 4, 5, 6, 0].map((dw) => (
          <div key={dw} className="panel tint" style={{ padding: 10, minHeight: 120 }}>
            <h3 style={{ marginBottom: 8 }}>{DAYS[dw]}</h3>
            {blocks.filter((b) => b.day_of_week === dw).sort((a, b) => (a.start_time < b.start_time ? -1 : 1)).map((b) => (
              <div key={b.start_time} style={{ background: 'var(--sheet)', borderRadius: 8, padding: '6px 8px', marginBottom: 6, fontSize: 14 }}>
                <b className="num">{hhmm(b.start_time)}</b><br /><span className="muted num">to {hhmm(b.end_time)}</span>
                <div className="row" style={{ justifyContent: 'space-between', marginTop: 2 }}>
                  <span className="faint small">{b.slot_minutes} min</span>
                  <button className="btn danger sm" style={{ padding: '0 6px' }} aria-label="Remove block"
                          onClick={() => setBlocks(blocks.filter((x) => x !== b))}>×</button>
                </div>
              </div>
            ))}
            {!blocks.some((b) => b.day_of_week === dw) && <span className="faint small">Closed</span>}
          </div>
        ))}
      </div>

      <div className="panel row top">
        <label className="field"><span>Day</span>
          <select value={add.day_of_week} onChange={(e) => setAdd({ ...add, day_of_week: Number(e.target.value) })}>
            {[1, 2, 3, 4, 5, 6, 0].map((d) => <option key={d} value={d}>{DAYS[d]}</option>)}
          </select></label>
        <label className="field"><span>From</span><input type="time" value={add.start_time} onChange={(e) => setAdd({ ...add, start_time: e.target.value })} /></label>
        <label className="field"><span>To</span><input type="time" value={add.end_time} onChange={(e) => setAdd({ ...add, end_time: e.target.value })} /></label>
        <label className="field"><span>Slot length</span>
          <select value={add.slot_minutes} onChange={(e) => setAdd({ ...add, slot_minutes: Number(e.target.value) })}>
            {[10, 15, 20, 30, 45, 60].map((m) => <option key={m} value={m}>{m} min</option>)}
          </select></label>
        <button className="btn ghost" style={{ alignSelf: 'end' }} onClick={() => { setBlocks([...blocks, { ...add }]); setSaved(false) }}>Add block</button>
      </div>

      <div className="row">
        <button className="btn" disabled={!dirty} onClick={save}>Save weekly hours</button>
        {dirty && <button className="btn ghost" onClick={reload}>Discard changes</button>}
        {saved && <span className="chip completed">Saved</span>}
      </div>
      {err && (
        <div className="notice alarm row" style={{ justifyContent: 'space-between' }}>
          <div><b>Not saved.</b> {err.message}{err.constraint && <div className="small">Refused by <code>{err.constraint}</code>. Your old hours are unchanged.</div>}</div>
          <span className="stamp blocked fresh">Blocked</span>
        </div>
      )}
      <p className="faint small">Existing bookings stay as they are even if they fall outside new hours.</p>
    </div>
  )
}

function Leave({ doctorId }) {
  const { data, error, loading, reload } = useApi(`/doctors/${doctorId}/unavailability`)
  const today = todayYmd()
  const [f, setF] = useState({ from: addDays(today, 7), to: addDays(today, 8), reason: 'On leave' })
  const [err, setErr] = useState(null)
  const [added, setAdded] = useState(null)

  const submit = async (e) => {
    e.preventDefault()
    setErr(null); setAdded(null)
    try {
      const r = await api(`/doctors/${doctorId}/unavailability`, {
        method: 'POST', body: { start_at: `${f.from}T00:00:00+05:30`, end_at: `${addDays(f.to, 1)}T00:00:00+05:30`, reason: f.reason },
      })
      setAdded(r); reload()
    } catch (e2) { setErr(e2) }
  }
  const remove = async (u) => {
    setErr(null)
    try { await api(`/doctors/${doctorId}/unavailability/${u.unavailability_id}`, { method: 'DELETE' }); reload() } catch (e) { setErr(e) }
  }

  return (
    <div className="two-col">
      <section>
        <h2 style={{ marginBottom: 10 }}>Upcoming time off</h2>
        <ErrorBox error={error} />
        {loading && !data ? <Loading /> : !data?.length ? <Empty>No leave planned.</Empty> : (
          <div className="ruled">
            {data.map((u) => (
              <div key={u.unavailability_id} className="row" style={{ padding: '12px 0', justifyContent: 'space-between' }}>
                <div><b>{u.reason || 'Unavailable'}</b><div className="muted small">{dateTime(u.start_at)} until {dateTime(u.end_at)}</div></div>
                <button className="btn ghost sm" onClick={() => remove(u)}>Remove</button>
              </div>
            ))}
          </div>
        )}
      </section>
      <form className="panel stack" onSubmit={submit}>
        <h2>Block days off</h2>
        <div className="row top">
          <label className="field"><span>First day</span><input type="date" value={f.from} onChange={(e) => setF({ ...f, from: e.target.value })} /></label>
          <label className="field"><span>Last day</span><input type="date" value={f.to} min={f.from} onChange={(e) => setF({ ...f, to: e.target.value })} /></label>
        </div>
        <label className="field"><span>Reason</span><input value={f.reason} onChange={(e) => setF({ ...f, reason: e.target.value })} /></label>
        <div><button className="btn">Block these days</button></div>
        {err && <div className="notice alarm"><b>Not added.</b> {err.message}{err.constraint && <div className="small">Refused by <code>{err.constraint}</code></div>}</div>}
        {added && <div className={`notice ${added.affected_appointments ? '' : 'ok'}`}>
          Blocked. {added.affected_appointments
            ? `${added.affected_appointments} existing booking${added.affected_appointments > 1 ? 's fall' : ' falls'} inside these days; contact those patients.`
            : 'No existing bookings are affected.'}
        </div>}
      </form>
    </div>
  )
}

function Reviews({ doctorId, doctor }) {
  const { data, loading } = useApi(`/doctors/${doctorId}/reviews`, { limit: 500 })
  if (loading && !data) return <Loading />
  const counts = [5, 4, 3, 2, 1].map((n) => [n, (data || []).filter((r) => r.rating === n).length])
  const max = Math.max(1, ...counts.map((c) => c[1]))
  return (
    <div className="two-col">
      <section>
        <h2 style={{ marginBottom: 10 }}>Latest reviews</h2>
        {!data?.length ? <Empty>No reviews yet.</Empty> : (
          <div className="ruled">
            {data.slice(0, 25).map((r) => (
              <div key={r.review_id} style={{ padding: '12px 0' }}>
                <div className="row" style={{ justifyContent: 'space-between' }}>
                  <b>{r.patient_name}</b><span style={{ color: 'var(--sticker)' }}>{'★'.repeat(r.rating)}<span style={{ color: 'var(--line)' }}>{'★'.repeat(5 - r.rating)}</span></span>
                </div>
                {r.comment && <p className="muted">{r.comment}</p>}
                <p className="faint small">{dateTime(r.created_at)}</p>
              </div>
            ))}
          </div>
        )}
      </section>
      <section className="panel tint">
        <div className="bigstat num">{Number(doctor?.average_rating || 0).toFixed(2)}</div>
        <p className="muted">average from {doctor?.rating_count || 0} reviews, kept up to date by a database trigger</p>
        <div className="stack" style={{ marginTop: 16, gap: 6 }}>
          {counts.map(([n, c]) => (
            <div key={n} className="row" style={{ gap: 8 }}>
              <span className="num" style={{ width: 18 }}>{n}★</span>
              <div style={{ flex: 1, height: 10, background: 'var(--sheet)', borderRadius: 5 }}>
                <div style={{ width: `${(c / max) * 100}%`, height: '100%', background: 'var(--scrub)', borderRadius: 5 }} />
              </div>
              <span className="num faint small" style={{ width: 28, textAlign: 'right' }}>{c}</span>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}

const LIST_FIELDS = ['qualifications', 'languages', 'services']
const toForm = (p) => ({
  bio: p?.bio || '', practising_since: p?.practising_since ?? '', hospital: p?.hospital || '', registration_no: p?.registration_no || '',
  ...Object.fromEntries(LIST_FIELDS.map((k) => [k, (p?.[k] || []).join(', ')])),
})
const fromForm = (f) => ({
  bio: f.bio.trim() || null,
  practising_since: f.practising_since === '' ? null : Number(f.practising_since),
  hospital: f.hospital.trim() || null,
  registration_no: f.registration_no.trim() || null,
  ...Object.fromEntries(LIST_FIELDS.map((k) => [k, f[k].split(',').map((x) => x.trim()).filter(Boolean)])),
})

function Profile({ doctorId, doctor }) {
  const { data, error, loading, reload } = useApi(`/doctors/${doctorId}/profile`)
  const [f, setF] = useState(toForm(null))
  const [err, setErr] = useState(null)
  const [saved, setSaved] = useState(false)
  useEffect(() => { if (!loading) setF(toForm(data)) }, [data, loading])
  const set = (k) => (e) => { setF({ ...f, [k]: e.target.value }); setSaved(false) }
  const thisYear = Number(todayYmd().slice(0, 4))
  const preview = { ...fromForm(f) }
  if (preview.practising_since) preview.years_experience = thisYear - preview.practising_since

  const save = async (e) => {
    e.preventDefault()
    setErr(null)
    try { await api(`/doctors/${doctorId}/profile`, { method: 'PUT', body: fromForm(f) }); setSaved(true); reload() } catch (x) { setErr(x) }
  }

  if (loading && !data) return <Loading />
  return (
    <div className="two-col">
      <form className="stack" onSubmit={save}>
        <ErrorBox error={error} />
        <label className="field"><span>About you</span>
          <textarea rows={5} maxLength={2000} value={f.bio} onChange={set('bio')} placeholder="How you work, what patients can expect" /></label>
        <label className="field"><span>Qualifications, separated by commas</span>
          <input value={f.qualifications} onChange={set('qualifications')} placeholder="MBBS, MD (Medicine)" /></label>
        <div className="row top">
          <label className="field" style={{ width: 160 }}><span>Practising since</span>
            <input type="number" min="1950" max={thisYear} value={f.practising_since} onChange={set('practising_since')} /></label>
          <label className="field grow"><span>Languages</span>
            <input value={f.languages} onChange={set('languages')} placeholder="English, Hindi, Marathi" /></label>
        </div>
        <label className="field"><span>Services, separated by commas</span>
          <input value={f.services} onChange={set('services')} placeholder="Diabetes follow-up, Health check-ups" /></label>
        <div className="row top">
          <label className="field grow"><span>Also consults at</span><input value={f.hospital} onChange={set('hospital')} /></label>
          <label className="field grow"><span>Registration number</span><input value={f.registration_no} onChange={set('registration_no')} /></label>
        </div>
        <div className="row">
          <button className="btn">Save profile</button>
          {saved && <span className="chip completed">Saved</span>}
        </div>
        <ErrorBox error={err} />
      </form>

      <section className="panel tint">
        <p className="faint small" style={{ marginBottom: 12 }}>What patients see on your booking page</p>
        <div className="doc-head" style={{ marginBottom: 16 }}>
          <Initials name={doctor?.full_name} size={56} />
          <div><h3>Dr {doctor?.full_name}</h3><p className="muted small">{doctor?.specialty}</p></div>
        </div>
        <DoctorProfile profile={preview} />
      </section>
    </div>
  )
}

const TITLES = { day: 'Day list', schedule: 'Weekly hours', leave: 'Leave', reviews: 'Reviews', profile: 'My profile' }
const INTRO = {
  day: 'Appointments for one day. Marking a visit as seen is what allows the patient to review it.',
  schedule: 'Patients can only book inside these hours. Overlapping blocks on the same day are refused.',
  leave: 'Blocked days disappear from the booking screen. Overlapping leave entries are refused.',
  reviews: 'Written by patients after a completed visit.',
  profile: 'Tell patients about yourself. This appears on your booking page.',
}

export default function DoctorDesk({ tab }) {
  const { doctorId, doctor, refreshPeople } = useSession()
  useEffect(() => { if (tab === 'reviews') refreshPeople() }, [tab]) // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div className="page">
      <PageHead title={TITLES[tab]}>
        {doctor && <><b>Dr {doctor.full_name}</b>, {doctor.specialty}. </>}{INTRO[tab]}
      </PageHead>
      {tab === 'day' && <DayList doctorId={doctorId} key={doctorId} />}
      {tab === 'schedule' && <WeeklyHours doctorId={doctorId} key={doctorId} />}
      {tab === 'leave' && <Leave doctorId={doctorId} key={doctorId} />}
      {tab === 'reviews' && <Reviews doctorId={doctorId} doctor={doctor} key={doctorId} />}
      {tab === 'profile' && <Profile doctorId={doctorId} doctor={doctor} key={doctorId} />}
    </div>
  )
}
