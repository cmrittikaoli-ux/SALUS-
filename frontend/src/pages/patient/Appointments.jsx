import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, useApi } from '../../api'
import { useSession } from '../../session'
import { dateTime, dayNum, relative, time } from '../../format'
import { Empty, ErrorBox, Loading, PageHead, StatusChip } from '../../components/ui'

const MONTH = new Intl.DateTimeFormat('en-IN', { timeZone: 'Asia/Kolkata', month: 'short' })

function Reminders({ id }) {
  const { data } = useApi(`/appointments/${id}/reminders`)
  if (!data) return null
  if (!data.length) return <div className="timeline-mini"><span>No reminders (booked less than 2 hours ahead)</span></div>
  return (
    <div className="timeline-mini">
      {data.map((r) => (
        <span key={r.reminder_id} className={r.sent_at ? 'sent' : ''}>
          Reminder {r.sent_at ? `sent ${dateTime(r.sent_at)}` : `due ${dateTime(r.remind_at)}`}
        </span>
      ))}
    </div>
  )
}

function ReviewForm({ appt, patientId, onDone }) {
  const [rating, setRating] = useState(0)
  const [comment, setComment] = useState('')
  const [err, setErr] = useState(null)
  const submit = async () => {
    setErr(null)
    try {
      await api('/reviews', { method: 'POST', body: { appointment_id: appt.appointment_id, patient_id: patientId, rating, comment: comment || null } })
      onDone()
    } catch (e) { setErr(e) }
  }
  return (
    <div className="panel tint stack" style={{ marginTop: 10 }}>
      <div className="row">
        <span>Your rating</span>
        <div className="starpick" role="radiogroup" aria-label="Rating">
          {[1, 2, 3, 4, 5].map((n) => (
            <button key={n} className={n <= rating ? 'on' : ''} onClick={() => setRating(n)} role="radio" aria-checked={n === rating} aria-label={`${n} star`}>★</button>
          ))}
        </div>
      </div>
      <textarea rows="2" placeholder="What was the visit like? (optional)" value={comment} onChange={(e) => setComment(e.target.value)} />
      <div className="row">
        <button className="btn" disabled={!rating} onClick={submit}>Post review</button>
        <span className="faint small">The database only accepts reviews for completed visits.</span>
      </div>
      <ErrorBox error={err} />
    </div>
  )
}

export default function Appointments() {
  const { patientId } = useSession()
  const [tab, setTab] = useState('upcoming')
  const { data, error, loading, reload } = useApi(`/patients/${patientId}/appointments`, { upcoming: tab === 'upcoming', limit: 60 })
  const [reviewing, setReviewing] = useState(null)
  const [err, setErr] = useState(null)

  const cancel = async (a) => {
    setErr(null)
    try { await api(`/appointments/${a.appointment_id}/cancel`, { method: 'POST' }); reload() } catch (e) { setErr(e) }
  }

  return (
    <div className="page">
      <PageHead title="Appointments" actions={<Link className="btn" to="/patient/find">Book a new one</Link>}>
        Cancelling frees the slot for someone else straight away.
      </PageHead>
      <div className="seg" role="group" aria-label="Which appointments" style={{ marginBottom: 12 }}>
        <button aria-pressed={tab === 'upcoming'} onClick={() => setTab('upcoming')}>Upcoming</button>
        <button aria-pressed={tab === 'past'} onClick={() => setTab('past')}>Past</button>
      </div>
      <ErrorBox error={error || err} />
      {loading && !data ? <Loading /> : data && !data.length ? (
        <Empty>{tab === 'upcoming' ? <>No upcoming appointments. <Link to="/patient/find">Find a doctor</Link></> : 'No past appointments.'}</Empty>
      ) : data && (
        <div className="ruled" style={{ maxWidth: 860 }}>
          {data.map((a) => (
            <div key={a.appointment_id} className="appt">
              <div className="datebox">
                <small>{MONTH.format(new Date(a.start_at))}</small>
                <b className="num">{dayNum(new Date(a.start_at).toLocaleDateString('en-CA', { timeZone: 'Asia/Kolkata' }))}</b>
                <small>{time(a.start_at)}</small>
              </div>
              <div>
                <div className="row" style={{ gap: 10 }}>
                  <h3>Dr {a.doctor_name}</h3><StatusChip status={a.status} />
                  {a.has_review && <span className="chip">Reviewed</span>}
                </div>
                <p className="muted">{a.specialty}{a.status === 'scheduled' ? `, ${relative(a.start_at)}` : ''}</p>
                {a.status === 'scheduled' && <Reminders id={a.appointment_id} />}
                {reviewing === a.appointment_id && (
                  <ReviewForm appt={a} patientId={patientId} onDone={() => { setReviewing(null); reload() }} />
                )}
              </div>
              <div className="row">
                {a.status === 'scheduled' && <button className="btn danger sm" onClick={() => cancel(a)}>Cancel</button>}
                {a.status === 'completed' && !a.has_review && reviewing !== a.appointment_id && (
                  <button className="btn ghost sm" onClick={() => setReviewing(a.appointment_id)}>Write a review</button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
