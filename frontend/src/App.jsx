import { useCallback, useEffect, useState } from 'react'
import { HashRouter, NavLink, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { SessionProvider, useSession } from './session'
import { API_URL } from './api'
import { Mark, SqlDrawer } from './components/ui'
import Login from './pages/Login'
import Home from './pages/patient/Home'
import FindDoctor from './pages/patient/FindDoctor'
import DoctorPage from './pages/patient/DoctorPage'
import Appointments from './pages/patient/Appointments'
import Medicines from './pages/patient/Medicines'
import Meals from './pages/patient/Meals'
import Wellness from './pages/patient/Wellness'
import DoctorDesk from './pages/doctor/DoctorDesk'
import UnderTheHood from './pages/UnderTheHood'

const PATIENT_NAV = [
  ['/patient', 'Home', 'home'],
  ['/patient/find', 'Find a doctor', 'find'],
  ['/patient/appointments', 'Appointments', 'appointments'],
  ['/patient/medicines', 'Medicines', 'medicines'],
  ['/patient/meals', 'Meals', 'meals'],
  ['/patient/wellness', 'Wellness', 'wellness'],
]
const DOCTOR_NAV = [
  ['/doctor', 'Day list', 'desk'],
  ['/doctor/schedule', 'Weekly hours', 'desk'],
  ['/doctor/leave', 'Leave', 'desk'],
  ['/doctor/reviews', 'Reviews', 'desk'],
  ['/doctor/profile', 'My profile', 'desk'],
]

function TopBar() {
  const { pathname } = useLocation()
  const nav = useNavigate()
  const s = useSession()
  const home = s.role === 'doctor' ? '/doctor' : '/patient'
  const name = s.role === 'doctor' ? `Dr ${s.doctor?.full_name || ''}` : s.patient?.full_name

  return (
    <header className="topbar">
      <a className="wordmark" href={`#${home}`}><Mark />Salus</a>
      <div className="seg" role="group" aria-label="View">
        <button aria-pressed={!pathname.startsWith('/hood')} onClick={() => nav(home)}>{s.role === 'doctor' ? 'My desk' : 'My health'}</button>
        <button aria-pressed={pathname.startsWith('/hood')} onClick={() => nav('/hood')}>Under the hood</button>
      </div>
      <div className="topbar-spacer" />
      <div className="whois">
        <span className="whois-name">{name}<small>{s.account.email}</small></span>
        <button className="btn ghost sm" onClick={s.logout}>Log out</button>
      </div>
    </header>
  )
}

function Rail({ onShowSql }) {
  const { pathname } = useLocation()
  const { role } = useSession()
  const items = pathname.startsWith('/hood') ? [['/hood', 'Checks and jobs']] : role === 'doctor' ? DOCTOR_NAV : PATIENT_NAV
  return (
    <nav className="rail" aria-label="Sections">
      {items.map(([to, label]) => (
        <NavLink key={to} to={to} end>{label}</NavLink>
      ))}
      <div className="rail-foot">
        {onShowSql && <button className="btn ghost sql-toggle" onClick={onShowSql}>Show the SQL</button>}
        <div className="rail-note">Connected to {API_URL.replace(/^https?:\/\//, '')}</div>
      </div>
    </nav>
  )
}

function screenFor(pathname) {
  if (pathname.startsWith('/patient/doctor')) return 'doctor'
  if (pathname.startsWith('/hood')) return 'hood'
  if (pathname.startsWith('/doctor')) return 'desk'
  const hit = PATIENT_NAV.find(([to]) => to === pathname)
  return hit ? hit[2] : null
}

function Shell() {
  const s = useSession()
  const { pathname } = useLocation()
  const ready = s.patients.length > 0 && s.doctors.length > 0
  const home = s.role === 'doctor' ? '/doctor' : '/patient'
  const screen = screenFor(pathname)
  const [sqlOpen, setSqlOpen] = useState(false)
  const closeSql = useCallback(() => setSqlOpen(false), [])
  useEffect(() => setSqlOpen(false), [pathname])

  if (s.checking) return <div className="loading login">Checking your session…</div>
  if (!s.account) return <Login />

  return (
    <div className="shell">
      <TopBar />
      <Rail onShowSql={screen ? () => setSqlOpen(true) : null} />
      <main className="sheet">
        {s.loadError ? (
          <div className="page">
            <h1>Can’t reach the Salus API</h1>
            <p className="muted" style={{ margin: '12px 0 20px', maxWidth: '62ch' }}>
              The page is looking for the backend at <code>{API_URL}</code>. Start it from the <code>backend</code> folder
              with <code>uvicorn app.main:app --reload</code>, then try again.
            </p>
            <button className="btn" onClick={s.refreshPeople}>Try again</button>
          </div>
        ) : !ready ? (
          <div className="loading">Loading patients and doctors…</div>
        ) : (
          <Routes>
            <Route path="/" element={<Navigate to={home} replace />} />
            {s.role === 'patient' && <>
              <Route path="/patient" element={<Home />} />
              <Route path="/patient/find" element={<FindDoctor />} />
              <Route path="/patient/doctor/:id" element={<DoctorPage />} />
              <Route path="/patient/appointments" element={<Appointments />} />
              <Route path="/patient/medicines" element={<Medicines />} />
              <Route path="/patient/meals" element={<Meals />} />
              <Route path="/patient/wellness" element={<Wellness />} />
            </>}
            {s.role === 'doctor' && <>
              <Route path="/doctor" element={<DoctorDesk tab="day" />} />
              <Route path="/doctor/schedule" element={<DoctorDesk tab="schedule" />} />
              <Route path="/doctor/leave" element={<DoctorDesk tab="leave" />} />
              <Route path="/doctor/reviews" element={<DoctorDesk tab="reviews" />} />
              <Route path="/doctor/profile" element={<DoctorDesk tab="profile" />} />
            </>}
            <Route path="/hood" element={<UnderTheHood />} />
            <Route path="*" element={<Navigate to={home} replace />} />
          </Routes>
        )}
      </main>
      <SqlDrawer screen={screen} open={sqlOpen} onOpen={() => setSqlOpen(true)} onClose={closeSql} />
    </div>
  )
}

export default function App() {
  return (
    <HashRouter>
      <SessionProvider>
        <Shell />
      </SessionProvider>
    </HashRouter>
  )
}
