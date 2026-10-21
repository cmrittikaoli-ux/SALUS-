import { useState } from 'react'
import { api, useApi } from '../../api'
import { useSession } from '../../session'
import { addDays, dayNum, dayOf, todayYmd, weekdayShort } from '../../format'
import { ErrorBox, Loading, PageHead } from '../../components/ui'

const TYPES = ['breakfast', 'lunch', 'dinner', 'snack']

function AddMeal({ patientId, defaultDate, onAdded }) {
  const [f, setF] = useState({ meal_date: defaultDate, meal_type: 'lunch', description: '', calories: '', is_planned: true })
  const [err, setErr] = useState(null)
  const [last, setLast] = useState(null)
  const set = (p) => setF((s) => ({ ...s, ...p }))
  const submit = async (e) => {
    e.preventDefault()
    setErr(null)
    try {
      const m = await api(`/patients/${patientId}/meals`, { method: 'POST', body: { ...f, calories: f.calories === '' ? null : Number(f.calories) } })
      setLast(m)
      set({ description: '', calories: '' })
      onAdded()
    } catch (e2) { setErr(e2) }
  }
  return (
    <form className="panel stack" onSubmit={submit}>
      <h2>Add a meal</h2>
      <div className="row top">
        <label className="field"><span>Day</span><input type="date" value={f.meal_date} onChange={(e) => set({ meal_date: e.target.value })} /></label>
        <label className="field"><span>Meal</span>
          <select value={f.meal_type} onChange={(e) => set({ meal_type: e.target.value })}>{TYPES.map((t) => <option key={t} value={t}>{t[0].toUpperCase() + t.slice(1)}</option>)}</select></label>
        <label className="field" style={{ width: 110 }}><span>Calories</span><input type="number" min="0" value={f.calories} onChange={(e) => set({ calories: e.target.value })} /></label>
      </div>
      <label className="field"><span>What’s on the plate</span>
        <input required value={f.description} onChange={(e) => set({ description: e.target.value })} placeholder="Dal tadka, jeera rice and salad" /></label>
      <div className="seg" role="group" aria-label="Planned or eaten" style={{ alignSelf: 'flex-start' }}>
        <button type="button" aria-pressed={f.is_planned} onClick={() => set({ is_planned: true })}>Planning it</button>
        <button type="button" aria-pressed={!f.is_planned} onClick={() => set({ is_planned: false })}>Already ate it</button>
      </div>
      <div className="row"><button className="btn">Add meal</button></div>
      <ErrorBox error={err} />
      {last && (last.diet_conflicts.length
        ? <div className="notice alarm">Added, but it clashes with your diet: {last.diet_conflicts.join('; ')}.</div>
        : <div className="notice ok">Added. Fits your dietary notes.</div>)}
    </form>
  )
}

export default function Meals() {
  const { patientId, patient } = useSession()
  const today = todayYmd()
  const [start, setStart] = useState(addDays(today, -3))
  const days = Array.from({ length: 7 }, (_, i) => addDays(start, i))
  const { data, error, loading, reload } = useApi(`/patients/${patientId}/meals`, { from: days[0], to: days[6] })
  const summary = useApi(`/patients/${patientId}/meals/summary`, { from: days[0], to: days[6] }, [data])

  const cell = (d, t) => (data || []).filter((m) => m.meal_date === d && m.meal_type === t)
  const sum = Object.fromEntries((summary.data || []).map((s) => [s.meal_date, s]))
  const maxKcal = Math.max(2400, ...Object.values(sum).map((s) => Math.max(s.planned_calories, s.consumed_calories)))
  const clashes = (data || []).filter((m) => m.diet_conflicts.length).length

  return (
    <div className="page stack lg">
      <PageHead title="Meal plan" actions={
        <div className="row">
          <button className="btn ghost" onClick={() => setStart(addDays(start, -7))}>Previous week</button>
          <button className="btn ghost" onClick={() => setStart(addDays(today, -3))}>This week</button>
          <button className="btn ghost" onClick={() => setStart(addDays(start, 7))}>Next week</button>
        </div>
      }>
        {patient?.dietary_notes
          ? <>Checked against your diet: <b>{patient.dietary_notes}</b>. {clashes ? `${clashes} meal${clashes > 1 ? 's' : ''} this week clash${clashes > 1 ? '' : 'es'} with it.` : 'Nothing this week clashes with it.'}</>
          : 'No dietary notes on file, so meals aren’t checked for clashes.'}
      </PageHead>

      <div className="legend">
        <span><i style={{ border: '1.5px dashed #d6b48f' }} />Planned</span>
        <span><i style={{ background: 'var(--scrub-tint)' }} />Eaten</span>
        <span><i style={{ background: 'var(--alarm-tint)', border: '1.5px solid var(--alarm)' }} />Clashes with diet</span>
      </div>

      <ErrorBox error={error} />
      {loading && !data ? <Loading /> : (
        <div className="mealgrid">
          <div />
          {days.map((d) => (
            <div key={d} className={`hd ${d === today ? 'today' : ''}`}>{weekdayShort(d)} {dayNum(d)}<small>{d === today ? 'Today' : dayOf(d).split(', ')[1] || ''}</small></div>
          ))}
          {TYPES.map((t) => (
            <FragmentRow key={t} t={t} days={days} cell={cell} />
          ))}
          <div className="rowlabel">Calories</div>
          {days.map((d) => {
            const s = sum[d]
            return (
              <div key={d}>
                <div className="kcalbar" title={s ? `${s.planned_calories} planned, ${s.consumed_calories} eaten` : 'Nothing logged'}>
                  <i style={{ height: `${((s?.planned_calories || 0) / maxKcal) * 100}%`, background: '#efdcbd' }} />
                  <i style={{ height: `${((s?.consumed_calories || 0) / maxKcal) * 100}%`, background: 'var(--scrub)' }} />
                </div>
                <div className="faint small num" style={{ padding: '2px 6px' }}>{s ? (s.consumed_calories || s.planned_calories) : 0} kcal</div>
              </div>
            )
          })}
        </div>
      )}

      <div style={{ maxWidth: 640 }}>
        <AddMeal patientId={patientId} defaultDate={today} onAdded={reload} />
      </div>
    </div>
  )
}

function FragmentRow({ t, days, cell }) {
  return (
    <>
      <div className="rowlabel">{t}</div>
      {days.map((d) => {
        const items = cell(d, t)
        if (!items.length) return <div key={d} className="meal none">—</div>
        return (
          <div key={d} className="stack" style={{ gap: 4 }}>
            {items.map((m) => (
              <div key={m.meal_id} className={`meal ${m.is_planned ? 'planned' : 'eaten'} ${m.diet_conflicts.length ? 'clash' : ''}`}>
                {m.description}
                <div className="kcal num">{m.calories ? `${m.calories} kcal` : ''}</div>
                {m.diet_conflicts.map((c) => <div key={c} className="why">{c}</div>)}
              </div>
            ))}
          </div>
        )
      })}
    </>
  )
}
