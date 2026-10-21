import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import { api, getToken, setToken } from './api'

const Ctx = createContext(null)

export function SessionProvider({ children }) {
  const [account, setAccount] = useState(null)
  const [checking, setChecking] = useState(!!getToken())
  const [patients, setPatients] = useState([])
  const [doctors, setDoctors] = useState([])
  const [loadError, setLoadError] = useState(null)

  const refreshMe = async () => {
    if (!getToken()) { setAccount(null); setChecking(false); return }
    try {
      setAccount(await api('/auth/me'))
    } catch (e) {
      if (e.status !== 401) setLoadError(e)
      setAccount(null)
    }
    setChecking(false)
  }

  const refreshPeople = async () => {
    try {
      const [p, d] = await Promise.all([
        api('/patients', { params: { limit: 500 } }),
        api('/doctors', { params: { limit: 500 } }),
      ])
      setPatients(p)
      setDoctors(d)
      setLoadError(null)
    } catch (e) {
      setLoadError(e)
    }
    if (getToken()) refreshMe()
  }

  const startSession = (s) => {
    setToken(s.token)
    setAccount(s)
    return s
  }
  const login = async (email, password) => startSession(await api('/auth/login', { method: 'POST', body: { email, password } }))
  const register = async (body) => startSession(await api('/auth/register', { method: 'POST', body }))
  const logout = async () => {
    try { await api('/auth/logout', { method: 'POST' }) } catch { /* already gone */ }
    setToken(null)
    setAccount(null)
  }

  useEffect(() => {
    refreshMe()
    const onGone = () => setAccount(null)
    window.addEventListener('salus:logged-out', onGone)
    return () => window.removeEventListener('salus:logged-out', onGone)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (account) refreshPeople() }, [account?.account_id]) // eslint-disable-line react-hooks/exhaustive-deps

  const value = useMemo(() => {
    const doctorId = account?.doctor_id || ''
    return {
      account, checking, login, register, logout, refreshMe,
      role: account?.role,
      patients, doctors, loadError, refreshPeople,
      patientId: account?.patient_id || '',
      doctorId,
      patient: account?.patient,
      // the list copy carries the live rating; fall back to the login record
      doctor: doctors.find((d) => d.doctor_id === doctorId) || account?.doctor,
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [account, checking, patients, doctors, loadError])

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export const useSession = () => useContext(Ctx)
