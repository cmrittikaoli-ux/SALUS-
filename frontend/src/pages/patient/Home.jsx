import { Link } from 'react-router-dom'
import { useApi } from '../../api'
import { useSession } from '../../session'
import { dayLong, firstName, greeting, relative, time } from '../../format'
import { Empty, ErrorBox, Loading } from '../../components/ui'
import DoseStrip from '../../components/DoseStrip'
import QuickLog from '../../components/QuickLog'
import Diary from '../../components/Diary'

const MEAL_ORDER = ['breakfast', 'lunch', 'dinner', 'snack']

export default function Home() {
  const { patientId, patient } = useSession()
  const { data, error, loading, reload } = useApi(`/patients/${patientId}/dashboard`)

  if (loading && !data) return <Loading />
  if (error) return <ErrorBox error={error} />
  const next = data.next_appointment
  const w = data.wellness_last_7_days

  return (
    <div className="page stack lg">
      <div>
        <h1>{greeting()}, {firstName(patient?.full_name)}</h1>
        <p className="muted" style={{ marginTop: 8 }}>
          {data.upcoming_appointments
            ? `You have ${data.upcoming_appointments} upcoming appointment${data.upcoming_appointments > 1 ? 's' : ''}.`
            : 'No appointments booked.'}
          {patient?.dietary_notes ? ` Diet on file: ${patient.dietary_notes}.` : ''}
        </p>
      </div>

      <div className="two-col">
        <div className="stack lg">
          <section>
            <div className="panel-title"><h2>Next appointment</h2><Link to="/patient/appointments">All appointments</Link></div>
            {next ? (
              <div className="token">
                <div className="token-stub">
                  <small>{relative(next.start_at)}</small>
                  <b>{time(next.start_at)}</b>
                </div>
                <div className="token-body">
                  <h3>Dr {next.doctor_name}</h3>
                  <p className="muted">{next.specialty}</p>
                  <p style={{ marginTop: 6 }}>{dayLong(next.start_at)}</p>
                </div>
              </div>
            ) : (
              <Empty>
                Nothing booked. <Link to="/patient/find">Find a doctor</Link> to book a slot.
              </Empty>
            )}
          </section>

          <section>
            <div className="panel-title"><h2>Today’s doses</h2><Link to="/patient/medicines">Medicines</Link></div>
            <DoseStrip patientId={patientId} />
          </section>

          {data.overlapping_prescription_pairs_now > 0 && (
            <div className="notice">
              <b>{data.overlapping_prescription_pairs_now} prescription{data.overlapping_prescription_pairs_now > 1 ? 's overlap' : ' overlaps'} today.</b>{' '}
              This is a date check, not medical advice. <Link to="/patient/medicines">See which ones</Link>
            </div>
          )}
        </div>

        <div className="stack lg">
          <section className="panel tint">
            <div className="panel-title"><h2>Your last 7 days</h2><Link to="/patient/wellness">Trends</Link></div>
            {w.days_logged ? (
              <div className="row" style={{ gap: 28 }}>
                <div><div className="bigstat num">{w.avg_mood}</div><span className="muted small">mood out of 10</span></div>
                <div><div className="bigstat num">{w.avg_sleep}</div><span className="muted small">hours of sleep</span></div>
                <div><div className="bigstat num">{(w.avg_water_ml / 1000).toFixed(1)}</div><span className="muted small">litres of water</span></div>
              </div>
            ) : <p className="muted">No logs this week yet.</p>}
            <p className="faint small" style={{ marginTop: 10 }}>Logged on {w.days_logged} of the last 7 days.</p>
          </section>

          <section>
            <h2 style={{ marginBottom: 12 }}>Log today</h2>
            <QuickLog patientId={patientId} onSaved={reload} />
          </section>

          <section>
            <div className="panel-title"><h2>Diary</h2><Link to="/patient/wellness">Past notes</Link></div>
            <Diary patientId={patientId} todayOnly />
          </section>

          <section>
            <div className="panel-title"><h2>Meals today</h2><Link to="/patient/meals">Week plan</Link></div>
            {data.meals_today.length ? (
              <div className="ruled">
                {data.meals_today.slice().sort((a, b) => MEAL_ORDER.indexOf(a.meal_type) - MEAL_ORDER.indexOf(b.meal_type)).map((m, i) => (
                  <div key={i} style={{ display: 'grid', gridTemplateColumns: '84px 1fr auto', gap: 12, padding: '8px 0' }}>
                    <span className="muted" style={{ textTransform: 'capitalize' }}>{m.meal_type}</span>
                    <span>{m.description}</span>
                    <span className="faint small num">{m.calories} kcal{m.is_planned ? ', planned' : ''}</span>
                  </div>
                ))}
              </div>
            ) : <p className="muted">No meals planned for today.</p>}
          </section>

          <section>
            <h2 style={{ marginBottom: 10 }}>Taking now</h2>
            {data.active_medications.length
              ? <ul style={{ margin: 0, paddingLeft: 18 }}>{data.active_medications.map((m) => <li key={m.medication_id}>{m.drug_name} <span className="muted">{m.dosage}</span></li>)}</ul>
              : <p className="muted">No active medicines.</p>}
          </section>
        </div>
      </div>
    </div>
  )
}
