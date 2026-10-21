import { useCallback, useEffect, useRef, useState } from 'react'

export const API_URL = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '')

export class ApiError extends Error {
  constructor(status, body) {
    const detail = typeof body?.detail === 'string'
      ? body.detail
      : Array.isArray(body?.detail)
        ? body.detail.map((d) => `${d.loc?.slice(-1)[0]}: ${d.msg}`).join('; ')
        : `Request failed (${status})`
    super(detail)
    this.status = status
    this.code = body?.error
    this.constraint = body?.constraint
    this.body = body
  }
}

// Login token, kept so a refresh doesn't log you out. A 401 on a request that
// carried it means the session is gone, so the app is told to show the login.
let token = (() => { try { return localStorage.getItem('salus.token') } catch { return null } })()
export const getToken = () => token
export function setToken(t) {
  token = t || null
  try { t ? localStorage.setItem('salus.token', t) : localStorage.removeItem('salus.token') } catch { /* private mode */ }
}

export async function api(path, { method = 'GET', body, params } = {}) {
  const url = new URL(API_URL + path)
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') url.searchParams.set(k, v)
    })
  }
  let res
  try {
    res = await fetch(url, {
      method,
      headers: {
        ...(body ? { 'Content-Type': 'application/json' } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: body ? JSON.stringify(body) : undefined,
    })
  } catch {
    throw new ApiError(0, { detail: `Can't reach the API at ${API_URL}. Start it with: uvicorn app.main:app --reload` })
  }
  const text = await res.text()
  const data = text ? JSON.parse(text) : null
  if (res.status === 401 && token) {
    setToken(null)
    window.dispatchEvent(new Event('salus:logged-out'))
  }
  if (!res.ok) throw new ApiError(res.status, data)
  return data
}

/** Fetch on mount and whenever `key` changes. Pass null as path to skip. */
export function useApi(path, params, deps = []) {
  const [state, setState] = useState({ data: null, error: null, loading: !!path })
  const seq = useRef(0)
  const paramsKey = JSON.stringify(params || {})

  const load = useCallback(async () => {
    if (!path) return
    const n = ++seq.current
    setState((s) => ({ ...s, loading: true, error: null }))
    try {
      const data = await api(path, { params })
      if (n === seq.current) setState({ data, error: null, loading: false })
    } catch (error) {
      if (n === seq.current) setState({ data: null, error, loading: false })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, paramsKey, ...deps])

  useEffect(() => { load() }, [load])
  return { ...state, reload: load }
}
