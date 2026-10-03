import { useCallback, useEffect, useMemo, useState } from 'react'

import * as api from '../api'
import { SESSION_EXPIRED, tokens } from '../api/client'
import { AuthContext } from './context'

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  // True until we know whether saved tokens are still valid, so a logged-in user
  // isn't briefly bounced to /login on page refresh.
  const [checking, setChecking] = useState(Boolean(tokens.refresh))

  useEffect(() => {
    if (!tokens.refresh) return
    api.auth.me()
      .then(setUser)
      .catch(() => tokens.clear())
      .finally(() => setChecking(false))
  }, [])

  useEffect(() => {
    const onExpired = () => setUser(null)
    window.addEventListener(SESSION_EXPIRED, onExpired)
    return () => window.removeEventListener(SESSION_EXPIRED, onExpired)
  }, [])

  const login = useCallback(async (username, password) => {
    await api.auth.login(username, password)
    setUser(await api.auth.me())
  }, [])

  const loginWithGoogle = useCallback(async (credential) => {
    await api.auth.googleLogin(credential)
    setUser(await api.auth.me())
  }, [])

  // After profile edits or linking Google, reload what the app knows about you.
  const refreshUser = useCallback(async () => {
    setUser(await api.auth.me())
  }, [])

  const register = useCallback(async (fields) => {
    await api.auth.register(fields)
    await login(fields.username, fields.password)
  }, [login])

  const logout = useCallback(async () => {
    await api.auth.logout().catch(() => {})
    setUser(null)
  }, [])

  const value = useMemo(
    () => ({ user, checking, login, loginWithGoogle, refreshUser, register, logout }),
    [user, checking, login, loginWithGoogle, refreshUser, register, logout],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
