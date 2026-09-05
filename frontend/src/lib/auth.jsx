// Authentication context: holds the signed-in user + their organization, and
// exposes login / signup / logout. The JWT itself lives in localStorage (see
// lib/api); this provider tracks the derived session state for the UI.
import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { api, getToken, onUnauthorized, setToken } from './api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [session, setSession] = useState({ user: null, org: null })
  // 'loading' until we've validated any existing token against /auth/me.
  const [status, setStatus] = useState(getToken() ? 'loading' : 'anonymous')

  const clear = useCallback(() => {
    setToken(null)
    setSession({ user: null, org: null })
    setStatus('anonymous')
  }, [])

  // If any API call 401s (expired/invalid token), drop to the login screen.
  useEffect(() => {
    onUnauthorized(() => clear())
  }, [clear])

  // On first load, validate a persisted token so a refresh keeps you signed in.
  useEffect(() => {
    if (!getToken()) return
    let alive = true
    api
      .me()
      .then((res) => {
        if (!alive) return
        setSession({ user: res.user, org: res.org })
        setStatus('authenticated')
      })
      .catch(() => {
        // onUnauthorized already handled 401; any other failure also resets.
        if (alive) clear()
      })
    return () => {
      alive = false
    }
  }, [clear])

  const adopt = useCallback((res) => {
    setToken(res.access_token)
    setSession({ user: res.user, org: res.org })
    setStatus('authenticated')
    return res
  }, [])

  const login = useCallback((body) => api.login(body).then(adopt), [adopt])
  const signup = useCallback((body) => api.signup(body).then(adopt), [adopt])
  const logout = useCallback(() => clear(), [clear])

  const value = {
    user: session.user,
    org: session.org,
    status,
    isAuthenticated: status === 'authenticated',
    isLoading: status === 'loading',
    login,
    signup,
    logout,
  }
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider')
  return ctx
}
