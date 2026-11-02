import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Button } from 'primereact/button'
import { Message } from 'primereact/message'
import { useTranslation } from 'react-i18next'
import { BrandMark } from '../components/BrandMark'
import { LangSeg } from '../components/LangSeg'
import { ThemeButton } from '../components/ThemeButton'
import { ApiError, apiFetch } from '../api/client'
import type { JobDetail, SessionInfo } from '../api/types'
import { Login } from '../screens/Login'
import { JobDetailView } from '../screens/jobs/JobDetailView'
import { applyTheme, preferredTheme, storedTheme, type Theme } from '../theme'

/** What the service puts into the page: where the job is, or that the link is spent. */
export interface JobViewConfig {
  dataUrl?: string
  expired?: boolean
  /** The same job in the console, absent when the console is switched off. */
  consoleUrl?: string
}

class LoadError extends Error {
  readonly status: number

  constructor(status: number) {
    super(`HTTP ${status}`)
    this.status = status
  }
}

async function loadJob(dataUrl: string): Promise<JobDetail> {
  const response = await fetch(dataUrl, { credentials: 'same-origin', cache: 'no-store' })
  if (!response.ok) throw new LoadError(response.status)
  return (await response.json()) as JobDetail
}

/**
 * The browser page the TestBench client opens for one job: the console's top
 * bar, where signing in to the console opens the same job there, and the
 * console's job detail below it.
 */
export function JobViewApp({ config }: { config: JobViewConfig }) {
  const { t } = useTranslation()
  // The console's stored choice applies here too: both live on the same origin.
  const [theme, setTheme] = useState<Theme>(() => storedTheme() ?? preferredTheme())
  useEffect(() => applyTheme(theme), [theme])

  // Already signed in to the console: straight to the job there; else the
  // console's login first, here on the page.
  const [signingIn, setSigningIn] = useState(false)
  const [busy, setBusy] = useState(false)
  const [signInError, setSignInError] = useState<ApiError | null>(null)
  const openConsole = async () => {
    try {
      await apiFetch<SessionInfo>('/session')
      window.location.assign(config.consoleUrl!)
    } catch {
      setSigningIn(true)
    }
  }
  const signIn = async (username: string, password: string) => {
    setBusy(true)
    setSignInError(null)
    try {
      await apiFetch<SessionInfo>('/session', {
        method: 'POST',
        body: JSON.stringify({ username, password }),
      })
      window.location.assign(config.consoleUrl!)
    } catch (cause) {
      setSignInError(cause instanceof ApiError ? cause : new ApiError('Sign-in failed', 0))
      setBusy(false)
    }
  }

  const dataUrl = config.expired ? undefined : config.dataUrl
  const job = useQuery({
    queryKey: ['job-view', dataUrl],
    queryFn: () => loadJob(dataUrl ?? ''),
    enabled: !!dataUrl,
    refetchInterval: (query) => (query.state.data?.status === 'running' ? 3_000 : false),
  })
  const expired = !dataUrl || (job.error instanceof LoadError && job.error.status === 401)

  useEffect(() => {
    if (job.data) document.title = `${job.data.agent_key} · TestBench AI Service`
  }, [job.data])

  const toggleTheme = () => setTheme(theme === 'light' ? 'dark' : 'light')

  if (signingIn) {
    return (
      <Login
        theme={theme}
        busy={busy}
        error={signInError}
        onSignIn={(username, password) => void signIn(username, password)}
        onToggleTheme={toggleTheme}
      />
    )
  }

  return (
    <div style={{ minHeight: '100%', display: 'flex', flexDirection: 'column' }}>
      <header
        style={{
          height: 52,
          flex: 'none',
          display: 'flex',
          alignItems: 'center',
          gap: 14,
          padding: '0 16px',
          borderBottom: '1px solid var(--color-divider)',
          background: 'var(--color-bg)',
          position: 'sticky',
          top: 0,
          zIndex: 5,
        }}
      >
        <BrandMark size="header" />
        <div style={{ flex: 1 }} />
        <LangSeg compact />
        <ThemeButton
          theme={theme}
          onToggle={toggleTheme}
          size={32}
        />
        {config.consoleUrl && (
          <div style={{ borderLeft: '1px solid var(--color-divider)', paddingLeft: 14 }}>
            <Button
              type="button"
              text
              label={t('login')}
              style={{ fontSize: 12 }}
              onClick={() => void openConsole()}
            />
          </div>
        )}
      </header>
      <main style={{ padding: 'var(--space-4, 16px)' }} data-testid="job-detail">
        {expired ? (
          <Message severity="warn" text={t('jobViewExpired')} />
        ) : job.isError ? (
          <Message severity="error" text={t('jobViewLoadFailed')} />
        ) : job.data ? (
          <JobDetailView job={job.data} />
        ) : null}
      </main>
    </div>
  )
}
