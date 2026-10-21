import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, useApi } from '../../api'
import { useSession } from '../../session'
import { dateTime, inr } from '../../format'
import { Empty, ErrorBox, Loading, PageHead, Rating } from '../../components/ui'
import MumbaiMap, { AREAS } from '../../components/MumbaiMap'

export const areaOf = (addr = '') => {
  const parts = (addr || '').split(', ')
  return parts.length > 2 ? parts[parts.length - 2] : ''
}

// remembered while the app is open, so "back" from a doctor keeps the search
let last = {
  specialty: 'Cardiologist', area: 'Dadar', here: { lat: 19.0178, lon: 72.8478 },
  budget: 2000, radius: 20, minRating: 0, within: false, w: { d: 40, f: 30, r: 30 },
}

export default function FindDoctor() {
  const { doctors } = useSession()
  const nav = useNavigate()
  const specialties = useApi('/specialties')
  const [q, setQ] = useState(last)
  const [rows, setRows] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [hot, setHot] = useState(null)
  const set = (patch) => setQ((s) => ({ ...s, ...patch }))

  useEffect(() => {
    last = q
    const t = setTimeout(async () => {
      setBusy(true)
      try {
        const data = await api('/doctors/search', {
          params: {
            lat: q.here.lat, lon: q.here.lon, specialty: q.specialty || undefined,
            max_budget: q.budget, radius_km: q.radius, min_rating: q.minRating, within_budget: q.within,
            w_distance: q.w.d, w_fee: q.w.f, w_rating: q.w.r, limit: 12,
          },
        })
        setRows(data)
        setError(null)
      } catch (e) { setError(e) }
      setBusy(false)
    }, 250)
    return () => clearTimeout(t)
  }, [q])

  const total = q.w.d + q.w.f + q.w.r || 1
  const pct = (v) => Math.round((v / total) * 100)

  const mapDoctors = useMemo(() => {
    const rank = new Map((rows || []).map((r, i) => [r.doctor_id, i + 1]))
    return doctors
      .filter((d) => !q.specialty || d.specialty === q.specialty)
      .map((d) => ({ ...d, rank: rank.get(d.doctor_id) }))
  }, [doctors, rows, q.specialty])

  return (
    <div className="page">
      <PageHead title="Find a doctor">
        Doctors are ranked on three things at once: how close they are, how their fee compares to your budget, and how
        patients rate them. Move the sliders to decide what matters most to you.
      </PageHead>

      <div className="finder">
        <div>
          <div className="filters">
            <label className="field"><span>Specialty</span>
              <select value={q.specialty} onChange={(e) => set({ specialty: e.target.value })}>
                <option value="">Any specialty</option>
                {(specialties.data || []).map((s) => <option key={s.specialty_id}>{s.name}</option>)}
              </select>
            </label>
            <label className="field"><span>You are near</span>
              <select value={q.area} onChange={(e) => {
                const a = AREAS.find((x) => x[0] === e.target.value)
                set({ area: a[0], here: { lat: a[1], lon: a[2] } })
              }}>
                {q.area === 'Pinned on map' && <option>Pinned on map</option>}
                {AREAS.map(([n]) => <option key={n}>{n}</option>)}
              </select>
            </label>
            <label className="field"><span>Budget: up to {inr(q.budget)}</span>
              <input type="range" min="300" max="3000" step="100" value={q.budget} onChange={(e) => set({ budget: Number(e.target.value) })} />
            </label>
            <label className="field"><span>Within</span>
              <select value={q.radius} onChange={(e) => set({ radius: Number(e.target.value) })}>
                {[5, 10, 20, 40].map((r) => <option key={r} value={r}>{r} km</option>)}
              </select>
            </label>
            <label className="field"><span>Minimum rating</span>
              <select value={q.minRating} onChange={(e) => set({ minRating: Number(e.target.value) })}>
                <option value="0">Any</option><option value="3">3 and above</option>
                <option value="3.5">3.5 and above</option><option value="4">4 and above</option>
              </select>
            </label>
            <label className="row small" style={{ alignSelf: 'end', paddingBottom: 9, gap: 8 }}>
              <input type="checkbox" checked={q.within} onChange={(e) => set({ within: e.target.checked })} />
              Hide doctors over budget
            </label>
          </div>

          <div className="weights">
            {[['d', 'Distance', 'c-dist'], ['f', 'Fee', 'c-fee'], ['r', 'Rating', 'c-rate']].map(([k, label, cls]) => (
              <label key={k}>
                <span className="row" style={{ justifyContent: 'space-between' }}>
                  <span><i className={cls} style={{ display: 'inline-block', width: 10, height: 10, borderRadius: 2, marginRight: 6 }} />{label}</span>
                  <b className="num">{pct(q.w[k])}%</b>
                </span>
                <input type="range" min="0" max="100" value={q.w[k]} onChange={(e) => set({ w: { ...q.w, [k]: Number(e.target.value) } })}
                       aria-label={`${label} weight`} />
              </label>
            ))}
          </div>

          <ErrorBox error={error} />
          {!rows && !error && <Loading what="Ranking doctors" />}
          {rows && !rows.length && (
            <Empty>No {q.specialty ? q.specialty.toLowerCase() + 's' : 'doctors'} within {q.radius} km match these filters. Try a wider radius or a higher budget.</Empty>
          )}
          {rows && rows.length > 0 && (
            <div className="ruled" style={{ opacity: busy ? 0.6 : 1, transition: 'opacity .15s' }}>
              {rows.map((r, i) => (
                <Link key={r.doctor_id} to={`/patient/doctor/${r.doctor_id}`} className={`result ${hot === r.doctor_id ? 'hot' : ''}`}
                      onMouseEnter={() => setHot(r.doctor_id)} onMouseLeave={() => setHot(null)}>
                  <div className="result-rank num">{i + 1}</div>
                  <div>
                    <div className="result-name">Dr {r.full_name}</div>
                    <div className="result-meta">
                      <span>{r.specialty}</span>
                      <span>{areaOf(r.address_text)}{areaOf(r.address_text) ? ', ' : ''}{r.distance_km} km</span>
                      <span>{inr(r.consultation_fee)}</span>
                      <Rating value={r.average_rating} count={r.rating_count} />
                    </div>
                    {r.next_available && <div className="small" style={{ marginTop: 4, color: 'var(--scrub)' }}>Next free: {dateTime(r.next_available)}</div>}
                  </div>
                  <div className="result-score"><b className="num">{Math.round(r.composite_score * 100)}</b><div className="faint small">score</div></div>
                  <div className="scorebar" title="How the score is made up">
                    <i className="c-dist" style={{ width: `${(q.w.d / total) * r.distance_score * 100}%` }} />
                    <i className="c-fee" style={{ width: `${(q.w.f / total) * r.fee_score * 100}%` }} />
                    <i className="c-rate" style={{ width: `${(q.w.r / total) * r.rating_score * 100}%` }} />
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>

        <div className="finder-map">
          <MumbaiMap here={q.here} radiusKm={q.radius} doctors={mapDoctors} hotId={hot} onHover={setHot}
                     onMove={(here) => set({ here, area: 'Pinned on map' })}
                     onPick={(id) => nav(`/patient/doctor/${id}`)} />
          <div className="map-caption">
            <span>Click anywhere to move yourself. Numbers match the list.</span>
            <span className="num">{q.here.lat.toFixed(3)}, {q.here.lon.toFixed(3)}</span>
          </div>
        </div>
      </div>
    </div>
  )
}
