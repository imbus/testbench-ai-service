import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { ApiError, apiFetch } from '../api/client'
import type { SessionInfo } from '../api/types'
import { clearStoredDraft } from './draft'

interface SessionState {
  session: SessionInfo | null
  loading: boolean
  error: string | null
  busy: boolean
  signIn: (username: string, password: string) => Promise<void>
  signOut: () => Promise<void>
  /** Re-read `GET /session`, e.g. after a refresh re-read the managed projects. */
  reload: () => Promise<void>
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

  // A failed re-read keeps the session as it is: a transient error is no
  // reason to sign the operator out, and an expired session surfaces as a
  // 401 on the next real request anyway.
  const reload = useCallback(async () => {
    try {
      setSession(await apiFetch<SessionInfo>('/session'))
    } catch {
      // keep the current session
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
      value={{ session, loading, busy, error, signIn, signOut, reload }}
    >
      {children}
    </SessionContext.Provider>
  )
}

/**
 * The session's `reload`, or a no-op outside a `SessionProvider` -- hooks
 * such as `useRefreshProjects` run in screens that tests render without one.
 */
export function useReloadSession(): () => Promise<void> {
  return useContext(SessionContext)?.reload ?? noReload
}

const noReload = async () => {}

export function useSession(): SessionState {
  const value = useContext(SessionContext)
  if (!value) throw new Error('useSession must be used inside a SessionProvider')
  return value
}
