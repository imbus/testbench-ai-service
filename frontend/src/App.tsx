import { useEffect, useState } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { NavRail } from './components/NavRail'
import { PendingBanner } from './components/PendingBanner'
import { RestartBanner } from './components/RestartBanner'
import { TopBar } from './components/TopBar'
import { AgentDetail } from './screens/AgentDetail'
import { Agents } from './screens/Agents'
import { ConfigSection } from './screens/ConfigSection'
import { Login } from './screens/Login'
import { Projects } from './screens/Projects'
import { PromptEditor } from './screens/PromptEditor'
import { Prompts } from './screens/Prompts'
import { Raw } from './screens/Raw'
import { Status } from './screens/Status'
import type { ConfigIssue } from './api/types'
import { useConfig, useMeta, useStatus } from './api/queries'
import { DraftProvider } from './state/draft'
import { useSession } from './state/session'
import { useTranslations, type Lang } from './i18n'
import { applyTheme, preferredTheme, storedTheme, type Theme } from './theme'

export function App() {
  const { session, loading, busy, error, signIn, signOut } = useSession()
  const meta = useMeta()
  const [lang, setLang] = useState<Lang>('de')
  const [theme, setTheme] = useState<Theme>(() => storedTheme() ?? preferredTheme())
  const [issues, setIssues] = useState<ConfigIssue[]>([])
  const t = useTranslations(lang)
  // Called unconditionally, ahead of the early returns below: this component
  // stays mounted across the loading -> signed-in transition, and hooks
  // called only on some renders of the same instance corrupt React's hook
  // order (a hard crash, not a lint nit). Gated on `session` rather than
  // dropped from the login/loading renders entirely -- both routes need a
  // session, and firing them at the Login screen would just poll a 401 every
  // 15 seconds for data nothing there uses.
  const config = useConfig({ enabled: !!session })
  const status = useStatus({ enabled: !!session })

  useEffect(() => applyTheme(theme), [theme])

  // App is one component instance across the whole session lifecycle (see
  // the hook-order note above), so an issue marker set while signed in would
  // otherwise survive in memory past sign-out -- clearStoredDraft() (in
  // signOut) only clears the draft, not this state. Keyed on `session`
  // itself rather than a click handler so an expired session (which also
  // surfaces as `session` becoming null, not just an explicit sign-out)
  // clears it too, before the next operator on a shared machine sees it.
  useEffect(() => {
    if (!session) setIssues([])
  }, [session])

  if (loading) return null

  if (!session) {
    return (
      <Login
        // From the unauthenticated /meta route: the operator should see which
        // TestBench they are signing into before they type a password.
        serverUrl={meta.data?.tb_server_url ?? ''}
        lang={lang}
        theme={theme}
        busy={busy}
        error={error}
        onSignIn={(username, password) => {
          void signIn(username, password).catch(() => undefined)
        }}
        onSetLang={setLang}
        onToggleTheme={() => setTheme(theme === 'light' ? 'dark' : 'light')}
      />
    )
  }

  // Derived from the status query rather than remembered from the apply
  // response: an operator who edits config.toml by hand, or who reloads the
  // console after applying, must still see the banner.
  const restartFields = status.data?.restart_required ?? []
  const service = status.data?.service

  return (
    // The draft is measured against the config *on disk* -- the draft is "what
    // will be written", and the running snapshot is fully defaulted, so
    // measuring against it would count every default the file omits as a
    // pending change. `disk` can be undefined while the query is in flight;
    // that state must NOT be coerced to `{}` here -- an empty object means
    // "the file genuinely has no keys" and would prune (and thereby destroy)
    // any queued removal edits before the config has even loaded.
    <DraftProvider saved={config.data?.disk}>
      <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
        <TopBar
          session={session}
          lang={lang}
          theme={theme}
          serviceLabel={service ? `${service.host}:${service.port}` : undefined}
          onToggleTheme={() => setTheme(theme === 'light' ? 'dark' : 'light')}
          onSetLang={setLang}
          onSignOut={() => void signOut()}
        />
        {session.is_admin && <PendingBanner lang={lang} onIssues={setIssues} />}
        <RestartBanner lang={lang} fields={restartFields} />
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
          <NavRail
            lang={lang}
            isAdmin={session.is_admin}
            overrideCount={status.data?.agents?.project_overrides ?? 0}
          />
          <main style={{ flex: 1, minWidth: 0 }}>
            <Routes>
              <Route path="/admin" element={<Navigate to="/admin/status" replace />} />
              <Route path="/" element={<Navigate to="/admin/status" replace />} />
              <Route path="/admin/status" element={<Status lang={lang} />} />
              <Route
                path="/admin/service"
                element={
                  <ConfigSection
                    section="service"
                    lang={lang}
                    isAdmin={session.is_admin}
                    issues={issues}
                  />
                }
              />
              <Route
                path="/admin/llm"
                element={
                  <ConfigSection
                    section="llm"
                    lang={lang}
                    isAdmin={session.is_admin}
                    issues={issues}
                  />
                }
              />
              <Route
                path="/admin/logging"
                element={
                  <ConfigSection
                    section="logging"
                    lang={lang}
                    isAdmin={session.is_admin}
                    issues={issues}
                  />
                }
              />
              {/* Both read-only for a non-admin, like Status -- so neither
                  route is gated; each screen renders through ReadOnlyField
                  instead. */}
              <Route
                path="/admin/agents"
                element={<Agents lang={lang} isAdmin={session.is_admin} />}
              />
              <Route
                path="/admin/agents/:agentKey"
                element={
                  <AgentDetail lang={lang} isAdmin={session.is_admin} issues={issues} />
                }
              />
              <Route
                path="/admin/projects"
                element={
                  <Projects lang={lang} isAdmin={session.is_admin} issues={issues} />
                }
              />
              <Route path="/admin/raw" element={<Raw lang={lang} />} />
              {/* Under /admin like every other screen: vite's `base` is
                  `/admin/` and static.py mounts the SPA at `/admin`, so a
                  route outside it click-throughs fine but 404s on a refresh,
                  a bookmark or an open-in-new-tab. Both ungated, like Agents
                  and Projects -- a non-admin sees the tree and the editor
                  read-only rather than losing the nav entry, which would
                  conceal information they are allowed to read. */}
              <Route path="/admin/prompts" element={<Prompts lang={lang} />} />
              <Route
                path="/admin/prompts/:lang/:agent"
                element={<PromptEditor lang={lang} isAdmin={session.is_admin} />}
              />
              <Route path="*" element={<Navigate to="/admin/status" replace />} />
            </Routes>
          </main>
        </div>
      </div>
    </DraftProvider>
  )
}
