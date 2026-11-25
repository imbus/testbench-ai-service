import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
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
  /** The session ended without the operator signing out (it expired, or was ended elsewhere). */
  expired?: boolean
}

const SessionContext = createContext<SessionState | null>(null)

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<SessionInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)
  const [expired, setExpired] = useState(false)
  // What the 401 listener reads: it is registered once and must not see a stale session.
  const sessionRef = useRef<SessionInfo | null>(null)
  sessionRef.current = session

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
    setUnauthorizedListener(() => {
      // Only a session that existed can expire: the 401 of the first probe on a
      // fresh page, or of a wrong password, is not an expiry.
      if (sessionRef.current) setExpired(true)
      setSession(null)
    })
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
      setExpired(false)
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
      // Deliberate: nothing to explain on the login screen.
      sessionRef.current = null
      setExpired(false)
      setSession(null)
      clearStoredDraft()
    }
  }, [])

  return (
    <SessionContext.Provider value={{ session, loading, busy, error, signIn, signOut, expired }}>
      {children}
    </SessionContext.Provider>
  )
}

export function useSession(): SessionState {
  const value = useContext(SessionContext)
  if (!value) throw new Error('useSession must be used inside a SessionProvider')
  return value
}
