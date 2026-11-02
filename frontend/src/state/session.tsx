import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { ApiError, apiFetch, setUnauthorizedListener } from '../api/client'
import type { SessionInfo } from '../api/types'
import { claimStoredDraft, clearStoredDraft } from './draft'

interface SessionState {
  session: SessionInfo | null
  loading: boolean
  error: ApiError | null
  busy: boolean
  signIn: (username: string, password: string) => Promise<void>
  signOut: () => Promise<void>
}

const SessionContext = createContext<SessionState | null>(null)

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<SessionInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)

  // A page reload still has the cookie; ask who we are rather than forcing a login.
  useEffect(() => {
    apiFetch<SessionInfo>('/session')
      .then(setSession)
      .catch(() => setSession(null))
      .finally(() => setLoading(false))
  }, [])

  // Any later 401 means the session expired or was revoked on the server:
  // back to the login screen rather than a shell whose every request fails.
  useEffect(() => {
    setUnauthorizedListener(() => setSession(null))
    return () => setUnauthorizedListener(null)
  }, [])

  const signIn = useCallback(async (username: string, password: string) => {
    setBusy(true)
    setError(null)
    try {
      const signedIn = await apiFetch<SessionInfo>('/session', {
        method: 'POST',
        body: JSON.stringify({ username, password }),
      })
      claimStoredDraft(signedIn.username)
      setSession(signedIn)
    } catch (cause) {
      setError(cause instanceof ApiError ? cause : new ApiError('Sign-in failed', 0))
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
      clearStoredDraft()
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
