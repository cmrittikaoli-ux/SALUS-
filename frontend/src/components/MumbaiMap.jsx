import { useRef } from 'react'

export const AREAS = [
  ['Colaba', 18.9067, 72.8147], ['Churchgate', 18.9322, 72.8264], ['Grant Road', 18.9633, 72.8156],
  ['Byculla', 18.979, 72.833], ['Lower Parel', 18.9953, 72.8258], ['Worli', 19.0176, 72.8174],
  ['Dadar', 19.0178, 72.8478], ['Matunga', 19.027, 72.857], ['Sion', 19.04, 72.862],
  ['Bandra West', 19.0596, 72.8295], ['Khar', 19.07, 72.837], ['Santacruz', 19.081, 72.841],
  ['Vile Parle', 19.1, 72.844], ['Juhu', 19.1075, 72.8263], ['Andheri West', 19.1363, 72.8277],
  ['Andheri East', 19.1136, 72.8697], ['Goregaon', 19.1646, 72.8493], ['Malad', 19.187, 72.848],
  ['Borivali', 19.2307, 72.8567], ['Kurla', 19.0726, 72.8845], ['Chembur', 19.0522, 72.9005],
  ['Ghatkopar', 19.086, 72.9081], ['Powai', 19.1176, 72.906], ['Mulund', 19.1726, 72.9425],
  ['Thane', 19.2183, 72.9781], ['Vashi', 19.0771, 72.9986],
]

// Stylised extent of the city (equirectangular, corrected for latitude)
const LAT0 = 18.895, LAT1 = 19.25, LON0 = 72.775, LON1 = 73.03
const W = 460
const KM_LAT = 111.0
const KM_LON = 111.0 * Math.cos((19.07 * Math.PI) / 180)
const PX_PER_KM = W / ((LON1 - LON0) * KM_LON)
const H = Math.round((LAT1 - LAT0) * KM_LAT * PX_PER_KM)

const px = (lat, lon) => [((lon - LON0) * KM_LON) * PX_PER_KM, ((LAT1 - lat) * KM_LAT) * PX_PER_KM]
const toLatLon = (x, y) => [LAT1 - y / PX_PER_KM / KM_LAT, LON0 + x / PX_PER_KM / KM_LON]

// A rough western shoreline, nudged seaward so clinics never land in the water
const COAST = [
  [18.895, 72.800], [18.93, 72.810], [18.96, 72.796], [19.0, 72.803], [19.03, 72.806],
  [19.06, 72.812], [19.09, 72.814], [19.12, 72.810], [19.16, 72.812], [19.2, 72.826], [19.25, 72.832],
]

export default function MumbaiMap({ here, radiusKm, doctors, hotId, onHover, onMove, onPick }) {
  const ref = useRef(null)
  const [hx, hy] = px(here.lat, here.lon)

  const handleClick = (e) => {
    const svg = ref.current
    const pt = svg.createSVGPoint()
    pt.x = e.clientX
    pt.y = e.clientY
    const p = pt.matrixTransform(svg.getScreenCTM().inverse())
    const [lat, lon] = toLatLon(p.x, p.y)
    onMove({ lat: Number(lat.toFixed(4)), lon: Number(lon.toFixed(4)) })
  }

  const sea = 'M0,0 ' + COAST.map(([la, lo]) => px(la, lo).join(',')).reverse().map((p) => 'L' + p).join(' ') + ` L0,${H} Z`
  const rings = [...new Set([5, 10, radiusKm])].sort((a, b) => a - b)

  return (
    <svg ref={ref} className="map" viewBox={`0 0 ${W} ${H}`} onClick={handleClick} role="img"
         aria-label="Map of Mumbai showing your location and nearby doctors. Click to move your location.">
      <defs>
        <pattern id="waves" width="14" height="8" patternUnits="userSpaceOnUse">
          <path d="M0 4 q3.5 -3 7 0 t7 0" fill="none" stroke="#c8dbe0" strokeWidth="1" />
        </pattern>
        <clipPath id="land"><rect width={W} height={H} rx="14" /></clipPath>
      </defs>
      <g clipPath="url(#land)">
        <rect width={W} height={H} fill="#fffaf0" />
        <path d={sea} fill="#e4eff1" />
        <path d={sea} fill="url(#waves)" />
        <text x="14" y={H * 0.55} transform={`rotate(-90 14 ${H * 0.55})`} textAnchor="middle"
              style={{ font: 'italic 13px var(--body)', fill: '#8aa9b0', letterSpacing: '0.3em' }}>Arabian Sea</text>

        {rings.map((r) => (
          <g key={r}>
            <circle cx={hx} cy={hy} r={r * PX_PER_KM} fill={r === radiusKm ? 'rgba(123,30,58,0.06)' : 'none'}
                    stroke={r === radiusKm ? '#7b1e3a' : '#dcc3a8'} strokeDasharray={r === radiusKm ? '0' : '4 5'} />
            <text x={hx + 4} y={hy - r * PX_PER_KM - 4} style={{ font: '12px var(--body)', fill: '#6e5a5f' }}>{r} km</text>
          </g>
        ))}

        {AREAS.map(([name, la, lo]) => {
          const [x, y] = px(la, lo)
          return <text key={name} x={x} y={y} textAnchor="middle"
                       style={{ font: '11px var(--body)', fill: '#a8969a' }}>{name}</text>
        })}

        {doctors.filter((d) => !d.rank).map((d) => {
          const [x, y] = px(d.latitude, d.longitude)
          return <circle key={d.doctor_id} cx={x} cy={y} r="2.5" fill="#d9bfc6" />
        })}
        {doctors.filter((d) => d.rank).sort((a, b) => b.rank - a.rank).map((d) => {
          const [x, y] = px(d.latitude, d.longitude)
          const hot = d.doctor_id === hotId
          return (
            <g key={d.doctor_id} transform={`translate(${x},${y})`} style={{ cursor: 'pointer' }}
               onMouseEnter={() => onHover?.(d.doctor_id)} onMouseLeave={() => onHover?.(null)}
               onClick={(e) => { e.stopPropagation(); onPick?.(d.doctor_id) }}>
              <circle r={hot ? 13 : 10} fill={d.rank === 1 ? '#e9a93a' : '#7b1e3a'} stroke="#fff" strokeWidth="2" />
              <text textAnchor="middle" dy="4" style={{ font: '700 11px var(--body)', fill: d.rank === 1 ? '#2b1a20' : '#fff' }}>{d.rank}</text>
              {hot && <text y="-17" textAnchor="middle" style={{ font: '700 12px var(--body)', fill: '#2b1a20' }}>Dr {d.full_name}</text>}
            </g>
          )
        })}

        <g transform={`translate(${hx},${hy})`} pointerEvents="none">
          <circle r="16" fill="rgba(233,169,58,0.3)" />
          <circle r="7" fill="#2b1a20" stroke="#e9a93a" strokeWidth="3" />
          <text y="30" textAnchor="middle" style={{ font: '700 12px var(--body)', fill: '#2b1a20' }}>You</text>
        </g>
      </g>
    </svg>
  )
}
