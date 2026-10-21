import { useState } from 'react'
import { useApi } from '../api'
import { useSession } from '../session'
import { ErrorBox, Mark } from '../components/ui'

function SignIn({ email, setEmail }) {
  const { login } = useSession()
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const demo = useApi('/auth/demo-accounts')

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true); setErr(null)
    try { await login(email, password) } catch (e2) { setErr(e2); setBusy(false) }
  }

  return (
    <>
      <form className="stack" onSubmit={submit}>
        <label className="field"><span>Email</span>
          <input type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} /></label>
        <label className="field"><span>Password</span>
          <input type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} /></label>
        <button className="btn" disabled={busy}>{busy ? 'Logging in…' : 'Log in'}</button>
        <ErrorBox error={err} />
      </form>

      {demo.data?.length > 0 && (
        <div className="demo-logins">
          <p className="small muted">Demo accounts. Every seeded patient and doctor uses the password <code>salus123</code>.</p>
          <div className="ruled">
            {demo.data.map((a) => (
              <button key={a.email} type="button" onClick={() => { setEmail(a.email); setPassword('salus123'); setErr(null) }}>
                <span><b>{a.name}</b><span className="faint small"> {a.role}</span></span>
                <span className="small muted">{a.note}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </>
  )
}

function SignUp() {
  const { register } = useSession()
  const [f, setF] = useState({ full_name: '', email: '', password: '', phone: '', date_of_birth: '', dietary_notes: '' })
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true); setErr(null)
    const body = Object.fromEntries(Object.entries(f).map(([k, v]) => [k, v.trim() === '' ? null : v]))
    try { await register(body) } catch (e2) { setErr(e2); setBusy(false) }
  }

  return (
    <form className="stack" onSubmit={submit}>
      <label className="field"><span>Full name</span><input required minLength={2} value={f.full_name} onChange={set('full_name')} /></label>
      <label className="field"><span>Email</span><input type="email" autoComplete="username" required value={f.email} onChange={set('email')} /></label>
      <label className="field"><span>Password, at least 8 characters</span>
        <input type="password" autoComplete="new-password" required minLength={8} value={f.password} onChange={set('password')} /></label>
      <div className="row top">
        <label className="field grow"><span>Phone (optional)</span><input value={f.phone} onChange={set('phone')} /></label>
        <label className="field grow"><span>Date of birth (optional)</span><input type="date" value={f.date_of_birth} onChange={set('date_of_birth')} /></label>
      </div>
      <label className="field"><span>Diet (optional)</span>
        <input placeholder="e.g. Vegetarian, lactose intolerant" value={f.dietary_notes} onChange={set('dietary_notes')} /></label>
      <button className="btn" disabled={busy}>{busy ? 'Creating account…' : 'Create account'}</button>
      <ErrorBox error={err} />
      <p className="faint small">Doctor accounts are set up by the clinic.</p>
    </form>
  )
}

export default function Login() {
  const { loadError } = useSession()
  const [mode, setMode] = useState('in')
  const [email, setEmail] = useState('')

  return (
    <div className="login">
      <div className="login-card">
        <div className="wordmark"><Mark />Salus</div>
        <h1>{mode === 'in' ? 'Welcome back' : 'Create your account'}</h1>
        <p className="muted">Appointments, medicines, meals and your daily log in one place.</p>
        <div className="seg" role="group" aria-label="Log in or sign up">
          <button aria-pressed={mode === 'in'} onClick={() => setMode('in')}>Log in</button>
          <button aria-pressed={mode === 'up'} onClick={() => setMode('up')}>New patient</button>
        </div>
        {loadError && <ErrorBox error={loadError} />}
        {mode === 'in' ? <SignIn email={email} setEmail={setEmail} /> : <SignUp />}
      </div>
    </div>
  )
}
