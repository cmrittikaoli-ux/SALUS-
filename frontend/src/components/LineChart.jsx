import { dayNum, weekdayShort } from '../format'

/**
 * Daily values as dots, a rolling average as a line.
 * rows: [{ date: 'YYYY-MM-DD', value, avg }]
 */
export default function LineChart({ rows, min, max, unit = '', color = '#7b1e3a', height = 190, ticks }) {
  const W = 720, H = height, L = 34, R = 10, T = 12, B = 26
  if (!rows.length) return null
  const first = new Date(rows[0].date), last = new Date(rows[rows.length - 1].date)
  const span = Math.max(1, (last - first) / 864e5)
  const x = (d) => L + ((new Date(d) - first) / 864e5 / span) * (W - L - R)
  const y = (v) => T + (1 - (v - min) / (max - min)) * (H - T - B)
  const tickVals = ticks || [min, (min + max) / 2, max]

  const avg = rows.filter((r) => r.avg != null)
  const path = avg.map((r, i) => `${i ? 'L' : 'M'}${x(r.date).toFixed(1)},${y(r.avg).toFixed(1)}`).join(' ')
  const labelEvery = Math.ceil(rows.length / 8)

  return (
    <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img">
      {tickVals.map((t) => (
        <g key={t}>
          <line x1={L} x2={W - R} y1={y(t)} y2={y(t)} stroke="#f3e5c6" />
          <text x={L - 8} y={y(t) + 4} textAnchor="end">{t}{unit}</text>
        </g>
      ))}
      {rows.map((r, i) => (i % labelEvery === 0 ? (
        <text key={r.date} x={x(r.date)} y={H - 6} textAnchor="middle">{weekdayShort(r.date)} {dayNum(r.date)}</text>
      ) : null))}
      {rows.filter((r) => r.value != null).map((r) => (
        <circle key={r.date} cx={x(r.date)} cy={y(r.value)} r="3.2" fill="#fff" stroke={color} strokeOpacity="0.55" strokeWidth="1.5">
          <title>{r.date}: {r.value}{unit}</title>
        </circle>
      ))}
      <path d={path} fill="none" stroke={color} strokeWidth="2.6" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  )
}
