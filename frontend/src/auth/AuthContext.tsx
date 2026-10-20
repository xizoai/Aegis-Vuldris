import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'

import { ApiError, authApi, setUnauthorizedHandler, tokenStore } from '../api/client'
import { AuthContext, type AuthContextValue } from './authContextValue'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthContextValue['user']>(null)
  const [isLoading, setIsLoading] = useState(true)

  const logout = useCallback(async () => {
    await authApi.logout()
    setUser(null)
  }, [])

  // When the API rejects the token (expired or revoked), drop the session so
  // the UI returns to the login screen instead of failing silently.
  useEffect(() => {
    setUnauthorizedHandler(() => {
      setUser(null)
      tokenStore.clear()
    })
  }, [])

  // Restore a session on load if a still-valid token is present.
  useEffect(() => {
    let cancelled = false

    async function restore() {
      if (!tokenStore.getValid()) {
        if (!cancelled) setIsLoading(false)
        return
      }
      try {
        const me = await authApi.me()
        if (!cancelled) setUser(me)
      } catch (error) {
        // A 401 is handled by the unauthorized handler; anything else just
        // means we cannot confirm a session, so treat it as signed out.
        if (error instanceof ApiError && error.status === 401) {
          tokenStore.clear()
        }
      } finally {
        if (!cancelled) setIsLoading(false)
      }
    }

    void restore()
    return () => {
      cancelled = true
    }
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    await authApi.login(email, password)
    const me = await authApi.me()
    setUser(me)
  }, [])

  const register = useCallback(async (email: string, password: string) => {
    await authApi.register(email, password)
    await authApi.login(email, password)
    const me = await authApi.me()
    setUser(me)
  }, [])

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      isAuthenticated: user !== null,
      isLoading,
      login,
      register,
      logout,
    }),
    [user, isLoading, login, register, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
