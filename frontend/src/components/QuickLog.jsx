import { useEffect, useState } from 'react'
import { api, useApi } from '../api'
import { todayYmd } from '../format'
import { ErrorBox } from './ui'

const GLASS = 250

export default function QuickLog({ patientId, onSaved }) {
  const today = todayYmd()
  const { data } = useApi(`/patients/${patientId}/wellness`, { from: today, to: today })
  const [mood, setMood] = useState(null)
  const [sleep, setSleep] = useState('')
  const [glasses, setGlasses] = useState(0)
  const [saved, setSaved] = useState(false)
  const [err, setErr] = useState(null)

  useEffect(() => {
    const log = data?.[0]
    setMood(log?.mood_score ?? null)
    setSleep(log?.sleep_hours ?? '')
    setGlasses(log?.water_intake_ml ? Math.round(log.water_intake_ml / GLASS) : 0)
    setSaved(false)
  }, [data])

  const save = async () => {
    setErr(null)
    try {
      await api(`/patients/${patientId}/wellness/${today}`, {
        method: 'PUT',
        body: { mood_score: mood, sleep_hours: sleep === '' ? null : Number(sleep), water_intake_ml: glasses * GLASS },
      })
      setSaved(true)
      onSaved?.()
    } catch (e) { setErr(e) }
  }

  return (
    <div className="stack">
      <div className="field">
        <span>Mood, 1 (low) to 10 (great)</span>
        <div className="moodpick">
          {Array.from({ length: 10 }, (_, i) => i + 1).map((n) => (
            <button key={n} aria-pressed={mood === n} onClick={() => { setMood(n); setSaved(false) }}>{n}</button>
          ))}
        </div>
      </div>
      <div className="row">
        <label className="field" style={{ width: 140 }}>
          <span>Sleep (hours)</span>
          <input type="number" min="0" max="24" step="0.5" value={sleep} onChange={(e) => { setSleep(e.target.value); setSaved(false) }} />
        </label>
        <div className="field">
          <span>Water: {glasses} glass{glasses === 1 ? '' : 'es'} ({(glasses * GLASS / 1000).toFixed(2)} L)</span>
          <div className="row" style={{ gap: 8 }}>
            <button className="btn ghost sm" onClick={() => { setGlasses(Math.max(0, glasses - 1)); setSaved(false) }} aria-label="One glass less">−</button>
            <div className="glasses" aria-hidden="true">
              {Array.from({ length: Math.max(8, glasses) }, (_, i) => <i key={i} className={i < glasses ? 'full' : ''} />)}
            </div>
            <button className="btn ghost sm" onClick={() => { setGlasses(glasses + 1); setSaved(false) }} aria-label="One more glass">+</button>
          </div>
        </div>
      </div>
      <div className="row">
        <button className="btn" onClick={save}>{data?.[0] ? 'Update today’s log' : 'Save today’s log'}</button>
        {saved && <span className="chip completed">Saved</span>}
      </div>
      <ErrorBox error={err} />
    </div>
  )
}
