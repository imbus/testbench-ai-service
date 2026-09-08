import { useEffect, useState } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { NavRail } from './components/NavRail'
import { TopBar } from './components/TopBar'
import { Login } from './screens/Login'
import { Status } from './screens/Status'
import { useMeta } from './api/queries'
import { useSession } from './state/session'
import { useTranslations, type Lang } from './i18n'
import { applyTheme, preferredTheme, storedTheme, type Theme } from './theme'

export function App() {
  const { session, loading, busy, error, signIn, signOut } = useSession()
  const meta = useMeta()
  const [lang, setLang] = useState<Lang>('de')
  const [theme, setTheme] = useState<Theme>(() => storedTheme() ?? preferredTheme())
  const t = useTranslations(lang)

  useEffect(() => applyTheme(theme), [theme])

  if (loading) return null

  if (!session) {
    return (
      <Login
        // From the unauthenticated /meta route: the operator should see which
        // TestBench they are signing into before they type a password.
        serverUrl={meta.data?.tb_server_url ?? ''}
        lang={lang}
        busy={busy}
        error={error}
        onSignIn={(username, password) => {
          void signIn(username, password).catch(() => undefined)
        }}
      />
    )
  }

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <TopBar
        session={session}
        lang={lang}
        theme={theme}
        onToggleTheme={() => setTheme(theme === 'light' ? 'dark' : 'light')}
        onSetLang={setLang}
        onSignOut={() => void signOut()}
      />
      {!session.is_admin && (
        <div
          style={{
            padding: '8px var(--space-4)',
            fontSize: 13,
            background: 'var(--color-surface)',
            borderBottom: '1px solid var(--color-divider)',
          }}
        >
          {t.readOnly}
        </div>
      )}
      <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
        <NavRail lang={lang} isAdmin={session.is_admin} />
        <main style={{ flex: 1, minWidth: 0 }}>
          <Routes>
            <Route path="/admin" element={<Navigate to="/admin/status" replace />} />
            <Route path="/" element={<Navigate to="/admin/status" replace />} />
            <Route path="/admin/status" element={<Status lang={lang} />} />
            <Route path="/admin/service" element={<div />} />
            <Route path="/admin/llm" element={<div />} />
            <Route path="/admin/logging" element={<div />} />
            <Route path="*" element={<Navigate to="/admin/status" replace />} />
          </Routes>
        </main>
      </div>
    </div>
  )
}
