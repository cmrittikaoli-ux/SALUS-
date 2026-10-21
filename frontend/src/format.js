export const TZ = 'Asia/Kolkata'

const dt = (opts) => new Intl.DateTimeFormat('en-IN', { timeZone: TZ, ...opts })
const fDay = dt({ weekday: 'short', day: 'numeric', month: 'short' })
const fTime = dt({ hour: 'numeric', minute: '2-digit', hour12: true })
const fDayLong = dt({ weekday: 'long', day: 'numeric', month: 'long' })
const fYmd = dt({ year: 'numeric', month: '2-digit', day: '2-digit' })

export const time = (iso) => fTime.format(new Date(iso)).replace(' ', ' ').toUpperCase()
export const day = (iso) => fDay.format(new Date(iso))
export const dayLong = (iso) => fDayLong.format(new Date(iso))
export const dateTime = (iso) => `${day(iso)}, ${time(iso)}`

/** 'YYYY-MM-DD' in IST for a Date */
export function ymd(d = new Date()) {
  const parts = Object.fromEntries(fYmd.formatToParts(d).map((p) => [p.type, p.value]))
  return `${parts.year}-${parts.month}-${parts.day}`
}
export const todayYmd = () => ymd(new Date())
export function addDays(ymdStr, n) {
  const d = new Date(ymdStr + 'T12:00:00+05:30')
  d.setDate(d.getDate() + n)
  return ymd(d)
}
/** Day label for a plain 'YYYY-MM-DD' */
export const dayOf = (ymdStr) => day(ymdStr + 'T12:00:00+05:30')
export const weekdayShort = (ymdStr) => dt({ weekday: 'short' }).format(new Date(ymdStr + 'T12:00:00+05:30'))
export const dayNum = (ymdStr) => Number(ymdStr.slice(8, 10))

export const inr = (n) => '₹' + Number(n).toLocaleString('en-IN', { maximumFractionDigits: 0 })
export const stars = (r) => Number(r).toFixed(1)

export function relative(iso) {
  const diff = new Date(iso) - new Date()
  const mins = Math.round(diff / 60000)
  const abs = Math.abs(mins)
  const fmt = (v, u) => (mins >= 0 ? `in ${v} ${u}` : `${v} ${u} ago`)
  if (abs < 60) return fmt(abs, abs === 1 ? 'minute' : 'minutes')
  const h = Math.round(abs / 60)
  if (h < 24) return fmt(h, h === 1 ? 'hour' : 'hours')
  const d = Math.round(h / 24)
  return fmt(d, d === 1 ? 'day' : 'days')
}

export const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
export const hhmm = (t) => {
  const [h, m] = t.split(':').map(Number)
  const am = h < 12
  const h12 = ((h + 11) % 12) + 1
  return `${h12}:${String(m).padStart(2, '0')} ${am ? 'AM' : 'PM'}`
}

export function greeting() {
  const h = Number(dt({ hour: 'numeric', hour12: false }).format(new Date()))
  return h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening'
}

export const firstName = (full = '') => full.split(' ')[0]

export const STATUS_LABEL = { scheduled: 'Booked', completed: 'Completed', cancelled: 'Cancelled', no_show: 'Missed' }
