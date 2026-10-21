import { useState } from 'react'
import { api, useApi } from '../api'
import { hhmm } from '../format'
import { Empty, ErrorBox, Loading } from './ui'

const shortDrug = (name) => name.replace(/\s+\d.*$/, '')

export default function DoseStrip({ patientId, on }) {
  const { data, error, loading, reload } = useApi(`/patients/${patientId}/doses`, { on })
  const [err, setErr] = useState(null)

  const respond = async (dose, taken) => {
    setErr(null)
    try {
      await api(`/medication-log/${dose.log_id}`, { method: 'POST', body: { taken } })
      reload()
    } catch (e) { setErr(e) }
  }

  if (loading && !data) return <Loading what="Loading doses" />
  if (error) return <ErrorBox error={error} />
  if (!data.length) return <Empty>No doses scheduled for this day.</Empty>

  const taken = data.filter((d) => d.taken).length
  return (
    <div className="stack">
      <p className="muted small">{taken} of {data.length} taken. Doses appear once their reminder has gone out.</p>
      <div className="blister">
        {data.map((d) => {
          const state = d.taken === true ? 'taken' : d.taken === false ? 'skipped' : d.sent_at ? 'due' : 'waiting'
          return (
            <div key={d.medication_reminder_id} className={`pill ${state}`} title={`${d.drug_name}, ${d.dosage}`}>
              <div className="cap">{state === 'taken' ? '✓' : state === 'skipped' ? '×' : ''}</div>
              <b className="small">{hhmm(d.reminder_time)}</b>
              <small>{shortDrug(d.drug_name)}</small>
              {d.log_id && state !== 'taken' && (
                <div className="acts">
                  <button onClick={() => respond(d, true)}>Taken</button>
                  {state !== 'skipped' && <button onClick={() => respond(d, false)}>Skip</button>}
                </div>
              )}
              {!d.log_id && <small className="faint">Not sent yet</small>}
            </div>
          )
        })}
      </div>
      <ErrorBox error={err} />
    </div>
  )
}
