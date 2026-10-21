import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, useApi } from '../../api'
import { useSession } from '../../session'
import { DAYS, addDays, dayLong, dayNum, dayOf, hhmm, inr, time, todayYmd, weekdayShort } from '../../format'
import { Empty, ErrorBox, Initials, Loading, Rating } from '../../components/ui'
import DoctorProfile from '../../components/DoctorProfile'

function groupSchedule(blocks) {
  const byDay = {}
  blocks.forEach((b) => { (byDay[b.day_of_week] ||= []).push(`${hhmm(b.start_time)} to ${hhmm(b.end_time)}`) })
  return byDay
}

export default function DoctorPage() {
  const { id } = useParams()
  const { patientId, patient } = useSession()
  const today = todayYmd()
  const doc = useApi(`/doctors/${id}`)
  const [stamp, setStamp] = useState(0)
  const slots = useApi(`/doctors/${id}/slots`, { date: today, days: 14 }, [stamp])
  const reviews = useApi(`/doctors/${id}/reviews`, { limit: 8 })
  const [date, setDate] = useState(today)
  const [pick, setPick] = useState(null)
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)

  if (doc.loading && !doc.data) return <Loading />
  if (doc.error) return <ErrorBox error={doc.error} />
  const d = doc.data
  const sched = groupSchedule(d.schedule)
  const days = Array.from({ length: 14 }, (_, i) => addDays(today, i))
  const daySlots = slots.data?.[date] || []

  const book = async () => {
    setBusy(true)
    try {
      const appt = await api('/appointments', { method: 'POST', body: { patient_id: patientId, doctor_id: id, start_at: pick.slot_start } })
      setResult({ ok: true, appt })
    } catch (e) {
      setResult({ ok: false, error: e })
    }
    setPick(null)
    setBusy(false)
    setStamp((n) => n + 1)
  }

  return (
    <div className="page">
      <p style={{ marginBottom: 14 }}><Link to="/patient/find">Back to results</Link></p>
      <div className="two-col">
        <div className="stack lg">
          <div className="doc-head">
            <Initials name={d.full_name} size={76} />
            <div>
              <h1>Dr {d.full_name}</h1>
              <p className="muted" style={{ marginTop: 8 }}>
                {d.specialty}{d.profile?.years_experience != null && `, ${d.profile.years_experience} years’ experience`}
              </p>
              <p className="muted small">{d.address_text}</p>
              <div className="row" style={{ marginTop: 12, gap: 20 }}>
                <span className="bigstat num" style={{ fontSize: 28 }}>{inr(d.consultation_fee)}</span>
                <Rating value={d.average_rating} count={d.rating_count} />
                {d.phone && <span className="muted">{d.phone}</span>}
              </div>
            </div>
          </div>

          <section>
            <h2 style={{ marginBottom: 12 }}>About</h2>
            <DoctorProfile profile={d.profile} />
          </section>

          <section>
            <h2 style={{ marginBottom: 12 }}>Pick a time</h2>
            <div className="datestrip" role="group" aria-label="Date">
              {days.map((ds) => {
                const n = slots.data?.[ds]?.length ?? 0
                return (
                  <button key={ds} aria-pressed={ds === date} className={n ? '' : 'off'}
                          onClick={() => { setDate(ds); setPick(null) }} title={`${n} free slots`}>
                    <small>{ds === today ? 'Today' : weekdayShort(ds)}</small>
                    <b className="num">{dayNum(ds)}</b>
                    <small>{n ? `${n} free` : 'full'}</small>
                  </button>
                )
              })}
            </div>

            <div style={{ marginTop: 16 }}>
              {slots.loading && !slots.data ? <Loading what="Finding free slots" />
                : daySlots.length ? (
                  <div className="slots">
                    {daySlots.map((s) => (
                      <button key={s.slot_start} aria-pressed={pick?.slot_start === s.slot_start} onClick={() => { setPick(s); setResult(null) }}>
                        {time(s.slot_start)}
                      </button>
                    ))}
                  </div>
                ) : <Empty>No free slots on {dayOf(date)}. The doctor is fully booked, on leave, or not working that day.</Empty>}
            </div>

            {pick && (
              <div className="panel tint row" style={{ marginTop: 16, justifyContent: 'space-between' }}>
                <span>Book <b>{time(pick.slot_start)}</b> on {dayLong(pick.slot_start)} for {patient?.full_name}, {inr(d.consultation_fee)} at the clinic.</span>
                <button className="btn" onClick={book} disabled={busy}>{busy ? 'Booking…' : 'Book this slot'}</button>
              </div>
            )}

            {result?.ok && (
              <div className="token" style={{ marginTop: 16 }}>
                <div className="token-stub">
                  <small>Token</small>
                  <b className="num">{result.appt.appointment_id.slice(0, 4).toUpperCase()}</b>
                </div>
                <div className="token-body row" style={{ justifyContent: 'space-between' }}>
                  <div>
                    <h3>{dayLong(result.appt.start_at)}, {time(result.appt.start_at)}</h3>
                    <p className="muted small">Reminders will go out 24 hours and 2 hours before. <Link to="/patient/appointments">See appointments</Link></p>
                  </div>
                  <span className="stamp fresh">Booked</span>
                </div>
              </div>
            )}
            {result && !result.ok && (
              <div className="notice alarm row" style={{ marginTop: 16, justifyContent: 'space-between' }}>
                <div>
                  <b>{result.error.status === 409 ? 'Someone just booked this slot.' : 'This slot can’t be booked.'}</b>
                  <div className="small">{result.error.message}</div>
                  {result.error.constraint && <div className="small">Refused by <code>{result.error.constraint}</code></div>}
                </div>
                <span className="stamp blocked fresh">Blocked</span>
              </div>
            )}
          </section>
        </div>

        <div className="stack lg">
          <section className="panel">
            <h2 style={{ marginBottom: 12 }}>Clinic hours</h2>
            <table className="ledger">
              <tbody>
                {[1, 2, 3, 4, 5, 6, 0].map((dw) => (
                  <tr key={dw}>
                    <td style={{ width: 60 }}><b>{DAYS[dw]}</b></td>
                    <td className={sched[dw] ? '' : 'faint'}>{sched[dw] ? sched[dw].join(', ') : 'Closed'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {d.schedule[0] && <p className="faint small" style={{ marginTop: 10 }}>{d.schedule[0].slot_minutes}-minute appointments.</p>}
          </section>

          <section>
            <h2 style={{ marginBottom: 6 }}>What patients say</h2>
            <p className="faint small" style={{ marginBottom: 8 }}>Only patients with a completed visit can review.</p>
            {reviews.data?.length ? (
              <div className="ruled">
                {reviews.data.map((r) => (
                  <div key={r.review_id} style={{ padding: '12px 0' }}>
                    <div className="row" style={{ justifyContent: 'space-between' }}>
                      <b>{r.patient_name}</b>
                      <span style={{ color: 'var(--sticker)', letterSpacing: 1 }} aria-label={`${r.rating} stars`}>{'★'.repeat(r.rating)}<span style={{ color: 'var(--line)' }}>{'★'.repeat(5 - r.rating)}</span></span>
                    </div>
                    {r.comment && <p className="muted" style={{ marginTop: 4 }}>{r.comment}</p>}
                  </div>
                ))}
              </div>
            ) : <p className="muted">No reviews yet.</p>}
          </section>
        </div>
      </div>
    </div>
  )
}
