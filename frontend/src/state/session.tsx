import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { ApiError, apiFetch } from '../api/client'
import type { SessionInfo } from '../api/types'

interface SessionState {
  session: SessionInfo | null
  loading: boolean
  error: string | null
  busy: boolean
  signIn: (username: string, password: string) => Promise<void>
  signOut: () => Promise<void>
}

const SessionContext = createContext<SessionState | null>(null)

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<SessionInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // A page reload still has the cookie; ask who we are rather than forcing a login.
  useEffect(() => {
    apiFetch<SessionInfo>('/session')
      .then(setSession)
      .catch(() => setSession(null))
      .finally(() => setLoading(false))
  }, [])

  const signIn = useCallback(async (username: string, password: string) => {
    setBusy(true)
    setError(null)
    try {
      setSession(
        await apiFetch<SessionInfo>('/session', {
          method: 'POST',
          body: JSON.stringify({ username, password }),
        }),
      )
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Sign-in failed')
      throw cause
    } finally {
      setBusy(false)
    }
  }, [])

  const signOut = useCallback(async () => {
    try {
      await apiFetch('/session', { method: 'DELETE' })
    } finally {
      setSession(null)
    }
  }, [])

  return (
    <SessionContext.Provider
      value={{ session, loading, busy, error, signIn, signOut }}
    >
      {children}
    </SessionContext.Provider>
  )
}

export function useSession(): SessionState {
  const value = useContext(SessionContext)
  if (!value) throw new Error('useSession must be used inside a SessionProvider')
  return value
}
