import { useState } from 'react'
import { useApi } from '../../api'
import { useSession } from '../../session'
import { addDays, dayOf, todayYmd } from '../../format'
import { ErrorBox, Loading, PageHead } from '../../components/ui'
import LineChart from '../../components/LineChart'
import QuickLog from '../../components/QuickLog'
import Diary from '../../components/Diary'

function describe(r) {
  if (r == null) return 'not enough days to compare'
  const a = Math.abs(r)
  const strength = a < 0.2 ? 'little or no' : a < 0.4 ? 'a weak' : a < 0.6 ? 'a moderate' : 'a strong'
  if (a < 0.2) return 'little or no link'
  return `${strength} ${r > 0 ? 'positive' : 'negative'} link`
}

export default function Wellness() {
  const { patientId } = useSession()
  const [days, setDays] = useState(30)
  const [tick, setTick] = useState(0)
  const today = todayYmd()
  const from = addDays(today, -(days - 1))
  const trend = useApi(`/patients/${patientId}/wellness/trend`, { from, to: today }, [tick])
  const weekly = useApi(`/patients/${patientId}/wellness/weekly`, { weeks: 6 }, [tick])
  const corr = useApi(`/patients/${patientId}/wellness/adherence-correlation`, { from: addDays(today, -29), to: today }, [tick])

  const rows = trend.data || []
  const mood = rows.map((r) => ({ date: r.log_date, value: r.mood_score, avg: r.mood_7d && Number(r.mood_7d) }))
  const sleep = rows.map((r) => ({ date: r.log_date, value: r.sleep_hours && Number(r.sleep_hours), avg: r.sleep_7d && Number(r.sleep_7d) }))
  const water = rows.map((r) => ({ date: r.log_date, value: r.water_intake_ml && r.water_intake_ml / 1000, avg: r.water_7d && Number(r.water_7d) / 1000 }))
  const c = corr.data

  return (
    <div className="page stack lg">
      <PageHead title="Wellness" actions={
        <div className="seg" role="group" aria-label="Period">
          {[14, 30, 60].map((n) => <button key={n} aria-pressed={days === n} onClick={() => setDays(n)}>{n} days</button>)}
        </div>
      }>
        A daily note of mood, sleep and water. Dots are single days; the line is your 7-day average.
        Salus describes trends only and doesn’t interpret them medically.
      </PageHead>

      <div className="two-col">
        <div className="stack lg">
          <ErrorBox error={trend.error} />
          {trend.loading && !trend.data ? <Loading /> : rows.length < 2 ? (
            <p className="muted">Log a few days to see trends here.</p>
          ) : (
            <>
              <section><h2 style={{ marginBottom: 6 }}>Mood</h2><LineChart rows={mood} min={1} max={10} ticks={[1, 4, 7, 10]} /></section>
              <section><h2 style={{ marginBottom: 6 }}>Sleep</h2><LineChart rows={sleep} min={3} max={11} unit="h" ticks={[4, 7, 10]} color="#4f5fa3" /></section>
              <section><h2 style={{ marginBottom: 6 }}>Water</h2><LineChart rows={water} min={0} max={4} unit="L" ticks={[0, 2, 4]} color="#2f8f8a" height={150} /></section>
            </>
          )}
        </div>

        <div className="stack lg">
          <section className="panel">
            <h2 style={{ marginBottom: 12 }}>Today</h2>
            <QuickLog patientId={patientId} onSaved={() => setTick((t) => t + 1)} />
          </section>

          <section>
            <h2 style={{ marginBottom: 6 }}>Diary</h2>
            <p className="muted small" style={{ marginBottom: 12 }}>The everyday bits: errands, visitors, what the weather did. The last 30 days.</p>
            <Diary patientId={patientId} />
          </section>

          <section>
            <h2 style={{ marginBottom: 10 }}>Week by week</h2>
            <table className="ledger num">
              <thead><tr><th>Week of</th><th className="r">Days</th><th className="r">Mood</th><th className="r">Sleep</th><th className="r">Change</th></tr></thead>
              <tbody>
                {(weekly.data || []).slice().reverse().map((w) => (
                  <tr key={w.week_start}>
                    <td>{dayOf(w.week_start)}</td>
                    <td className="r">{w.days_logged}</td>
                    <td className="r">{w.avg_mood}</td>
                    <td className="r">{w.avg_sleep}h</td>
                    <td className="r" style={{ color: w.mood_change > 0 ? 'var(--ok)' : w.mood_change < 0 ? 'var(--alarm)' : undefined }}>
                      {w.mood_change == null ? '' : `${w.mood_change > 0 ? '+' : ''}${Number(w.mood_change).toFixed(2)}`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          {c && c.days_compared > 0 && (
            <section className="panel tint">
              <h2 style={{ marginBottom: 10 }}>Medicines and mood</h2>
              <p>
                Over {c.days_compared} days with both a dose record and a wellness log, there was{' '}
                <b>{describe(c.corr_adherence_mood == null ? null : Number(c.corr_adherence_mood))}</b> between taking every dose and mood
                {c.corr_adherence_mood != null && <span className="muted"> (r = {Number(c.corr_adherence_mood).toFixed(2)})</span>}.
              </p>
              {c.avg_mood_full_adherence != null && c.avg_mood_partial_adherence != null && (
                <div className="row" style={{ gap: 28, marginTop: 14 }}>
                  <div><div className="bigstat num">{c.avg_mood_full_adherence}</div><span className="muted small">mood on days every dose was taken</span></div>
                  <div><div className="bigstat num">{c.avg_mood_partial_adherence}</div><span className="muted small">mood on other days</span></div>
                </div>
              )}
              <p className="faint small" style={{ marginTop: 12 }}>{c.note}</p>
            </section>
          )}
        </div>
      </div>
    </div>
  )
}
