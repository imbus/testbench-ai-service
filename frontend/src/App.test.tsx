import { useState } from 'react'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, MemoryRouter, RouterProvider } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { App } from './App'
import * as sessionState from './state/session'

const asSession = (session: unknown, loading = false) =>
  vi.spyOn(sessionState, 'useSession').mockReturnValue({
    session,
    loading,
    busy: false,
    error: null,
    signIn: vi.fn(),
    signOut: vi.fn(),
  } as never)

beforeEach(() => {
  window.localStorage.clear()
  vi.stubGlobal(
    'fetch',
    vi.fn(() =>
      Promise.resolve(
        new Response(JSON.stringify({ tb_server_url: 'https://tb:9443/api/' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    ),
  )
})

afterEach(() => vi.restoreAllMocks())

// A data router, not `<MemoryRouter>`: `PromptEditor`'s `useBlocker` (Task 15
// fix round, Finding 2) only works inside one, and the two `/admin/prompts` route
// tests below mount it. `App`'s own nested `<Routes>` tree needs no change to
// sit under this single catch-all data route -- see main.tsx's own comment.
const renderApp = ({
  isAdmin = false,
  route = '/admin/status',
}: { isAdmin?: boolean; route?: string } = {}) => {
  asSession({
    username: 'a.mueller',
    roles: isAdmin ? ['Administrator'] : ['Test Manager'],
    is_admin: isAdmin,
    tb_server_url: 'https://tb:9443/api/',
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const router = createMemoryRouter([{ path: '*', element: <App /> }], { initialEntries: [route] })
  return render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
}

// These three exercise the pre-session states (no session yet, still
// loading) that `renderApp`'s always-authenticated session mock cannot
// produce, so they render inline rather than going through it.
const renderWithoutSession = () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/admin/status']}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

test('shows the sign-in screen when there is no session', async () => {
  asSession(null)
  renderWithoutSession()
  await waitFor(() =>
    expect(screen.getByRole('button', { name: /anmelden/i })).toBeInTheDocument(),
  )
})

test('shows the shell when signed in', async () => {
  renderApp({ isAdmin: true })
  await waitFor(() => expect(screen.getByRole('navigation')).toBeInTheDocument())
  expect(screen.getByText('a.mueller')).toBeInTheDocument()
})

test('shows a read-only notice to a non-admin', async () => {
  renderApp({ isAdmin: false })
  await waitFor(() =>
    expect(screen.getByText(/nur lesend/i)).toBeInTheDocument(),
  )
})

test('renders nothing decisive while the session is still loading', () => {
  asSession(null, true)
  renderWithoutSession()
  expect(screen.queryByRole('button', { name: /anmelden/i })).toBeNull()
})

it('shows the pending-changes banner when the draft has edits', async () => {
  window.localStorage.setItem('tbai_admin_draft', JSON.stringify({ port: 9999 }))

  renderApp({ isAdmin: true })

  // App defaults to German (lang state starts as 'de'), so the banner text
  // is the German translation of "unapplied changes" -- see i18n/de.ts.
  expect(await screen.findByRole('status')).toHaveTextContent('nicht übernommene Änderungen')
})

it('shows no pending-changes banner for a clean draft', async () => {
  renderApp({ isAdmin: true })

  await screen.findByRole('navigation')
  expect(screen.queryByText(/nicht übernommene Änderungen/)).not.toBeInTheDocument()
})

it('does not show the pending-changes banner to a non-admin', async () => {
  // A read-only session cannot apply anything, so a count of queued changes
  // would be an offer it cannot honour.
  window.localStorage.setItem('tbai_admin_draft', JSON.stringify({ port: 9999 }))

  renderApp({ isAdmin: false })

  await screen.findByRole('navigation')
  expect(screen.queryByText(/nicht übernommene Änderungen/)).not.toBeInTheDocument()
})

it('routes /admin/raw to the raw config screen', async () => {
  renderApp({ isAdmin: true, route: '/admin/raw' })

  expect(await screen.findByRole('heading', { name: 'config.toml' })).toBeInTheDocument()
})

// --- Fix round 1: the issues wiring (App -> PendingBanner -> DiffDialog and
// back down into ConfigSection) had no test at the seam that actually
// connects it. These four exercise that seam directly, mocking fetch per
// URL now that App itself calls useConfig/useStatus (Status and Config
// responses below are minimal but shaped like the real endpoints).

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
}

const CONFIG_OK = { running: {}, disk: {}, config_path: '/tmp/config.toml' }

const STATUS_OK = {
  service: { version: '1', host: 'h', port: 8010, debug: false, uptime_seconds: 1, language: 'de' },
  testbench: { url: 'https://tb:9443/api/', reachable: true, detail: null },
  api_keys: [],
  agents: { total: 0, enabled: 0, project_overrides: 0, projects: 0 },
  log_file: 'x',
  in_flight_tasks: 0,
  restart_required: [],
}

const PREVIEW_INVALID = {
  valid: false,
  issues: [
    { path: 'port', message: 'Input should be a valid integer', toml_section: '[testbench-ai-service]' },
  ],
  diffs: [],
  restart_required: [],
  in_flight_tasks: 0,
  toml: '',
}

const PREVIEW_VALID = {
  valid: true,
  issues: [],
  diffs: [
    {
      path: '/tmp/config.toml',
      diff: '-port = 8010\n+port = 9999\n',
      added: 1,
      removed: 1,
    },
  ],
  restart_required: ['port'],
  in_flight_tasks: 0,
  toml: '[testbench-ai-service]\nport = 9999\n',
}

const APPLY_OK = {
  written: ['/tmp/config.toml'],
  backup: null,
  restart_required: ['port'],
  reloaded: false,
  in_flight_tasks: 0,
}

/**
 * Routes the App-level fetch stub by URL/method: /meta, /config, /status
 * each get a response shaped like their real endpoint (App now queries all
 * three itself), /config/preview answers with `previewResponses` in order
 * (repeating the last one once exhausted), and /config/apply answers with
 * `applyResponse`.
 */
function installFetchRouter({
  previewResponses,
  applyResponse,
}: {
  previewResponses: unknown[]
  applyResponse?: unknown
}) {
  let previewCall = 0
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string, init?: RequestInit) => {
      const method = (init?.method ?? 'GET').toUpperCase()
      if (url.endsWith('/meta')) return jsonResponse({ tb_server_url: 'https://tb:9443/api/' })
      if (url.endsWith('/config') && method === 'GET') return jsonResponse(CONFIG_OK)
      if (url.endsWith('/status')) return jsonResponse(STATUS_OK)
      if (url.endsWith('/config/preview')) {
        const body = previewResponses[Math.min(previewCall, previewResponses.length - 1)]
        previewCall += 1
        return jsonResponse(body)
      }
      if (url.endsWith('/config/apply')) return jsonResponse(applyResponse ?? {})
      return jsonResponse({})
    }),
  )
}

it('marks the invalid field after a preview rejects the draft', async () => {
  window.localStorage.setItem('tbai_admin_draft', JSON.stringify({ port: 9999 }))
  installFetchRouter({ previewResponses: [PREVIEW_INVALID] })

  renderApp({ isAdmin: true, route: '/admin/service' })
  await screen.findByRole('navigation')
  await userEvent.click(screen.getByRole('button', { name: 'Diff anzeigen' }))

  const dialog = await screen.findByRole('dialog')
  expect(within(dialog).getByText(/Input should be a valid integer/)).toBeInTheDocument()
  expect(await screen.findByLabelText('port')).toHaveAttribute('aria-invalid', 'true')
})

it('clears the marker after a successful apply', async () => {
  window.localStorage.setItem('tbai_admin_draft', JSON.stringify({ port: 9999 }))
  installFetchRouter({
    previewResponses: [PREVIEW_INVALID, PREVIEW_VALID],
    applyResponse: APPLY_OK,
  })

  renderApp({ isAdmin: true, route: '/admin/service' })
  await screen.findByRole('navigation')

  await userEvent.click(screen.getByRole('button', { name: 'Diff anzeigen' }))
  expect(await screen.findByLabelText('port')).toHaveAttribute('aria-invalid', 'true')
  await userEvent.click(screen.getByRole('button', { name: 'Schließen' }))

  // Reopening mounts a fresh DiffDialog, which re-previews -- this time the
  // draft is reported valid, so Apply is offered.
  await userEvent.click(screen.getByRole('button', { name: 'Diff anzeigen' }))
  // Scoped to the dialog: the pending banner carries an Apply of its own
  // (it opens this dialog), so the name is ambiguous page-wide.
  await userEvent.click(
    within(await screen.findByRole('dialog')).getByRole('button', { name: 'Übernehmen' }),
  )

  await waitFor(() =>
    expect(screen.getByLabelText('port')).not.toHaveAttribute('aria-invalid', 'true'),
  )
})

it('a later VALID preview clears a marker an earlier invalid preview set (FIX 2)', async () => {
  // Regression guard for FIX 2: DiffDialog's preview effect used to report
  // issues to `onIssues` only when a preview came back invalid, never
  // clearing them on a later valid preview. An operator who fixes the field
  // and reopens the dialog -- without discarding, applying or signing out --
  // must see the marker clear as soon as the fixed preview comes back valid,
  // before Apply is ever clicked.
  window.localStorage.setItem('tbai_admin_draft', JSON.stringify({ port: 9999 }))
  installFetchRouter({ previewResponses: [PREVIEW_INVALID, PREVIEW_VALID] })

  renderApp({ isAdmin: true, route: '/admin/service' })
  await screen.findByRole('navigation')

  await userEvent.click(screen.getByRole('button', { name: 'Diff anzeigen' }))
  expect(await screen.findByLabelText('port')).toHaveAttribute('aria-invalid', 'true')
  await userEvent.click(screen.getByRole('button', { name: 'Schließen' }))

  // Reopening mounts a fresh DiffDialog, which re-previews -- this time the
  // draft is reported valid. The marker must clear without applying.
  await userEvent.click(screen.getByRole('button', { name: 'Diff anzeigen' }))

  await waitFor(() =>
    expect(screen.getByLabelText('port')).not.toHaveAttribute('aria-invalid', 'true'),
  )
})

it('clears the marker when the draft is discarded', async () => {
  window.localStorage.setItem('tbai_admin_draft', JSON.stringify({ port: 9999 }))
  installFetchRouter({ previewResponses: [PREVIEW_INVALID] })

  renderApp({ isAdmin: true, route: '/admin/service' })
  await screen.findByRole('navigation')

  await userEvent.click(screen.getByRole('button', { name: 'Diff anzeigen' }))
  expect(await screen.findByLabelText('port')).toHaveAttribute('aria-invalid', 'true')
  await userEvent.click(screen.getByRole('button', { name: 'Schließen' }))

  await userEvent.click(screen.getByRole('button', { name: 'Verwerfen' }))

  await waitFor(() =>
    expect(screen.getByLabelText('port')).not.toHaveAttribute('aria-invalid', 'true'),
  )
})

const APPLY_REJECTED_DETAIL = {
  message: 'The configuration is not valid and was not written.',
  issues: [
    { path: 'port', message: 'Input should be a valid integer', toml_section: '[testbench-ai-service]' },
  ],
}

it('a structured 422 apply rejection does not loop the renderer (regression for the DiffDialog infinite-loop bug)', async () => {
  // Regression guard for FIX 1: an apply rejected with a structured 422 used
  // to enter an unbounded render loop -- the issues array derived from
  // `apply.error` was recomputed fresh on every render and used as a
  // `useEffect` dependency, so `onIssues` firing (which sets state in App)
  // produced a new array identity that re-fired the effect, forever. React
  // reports that specific failure mode as "Maximum update depth exceeded".
  // Driven through the real App (not DiffDialog in isolation) because the
  // loop only manifests once `onIssues` actually reaches `App`'s state
  // setter -- a dialog-only test with a stub `onIssues` would not reproduce
  // it.
  window.localStorage.setItem('tbai_admin_draft', JSON.stringify({ port: 9999 }))
  installFetchRouter({ previewResponses: [PREVIEW_VALID] })
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string, init?: RequestInit) => {
      const method = (init?.method ?? 'GET').toUpperCase()
      if (url.endsWith('/meta')) return jsonResponse({ tb_server_url: 'https://tb:9443/api/' })
      if (url.endsWith('/config') && method === 'GET') return jsonResponse(CONFIG_OK)
      if (url.endsWith('/status')) return jsonResponse(STATUS_OK)
      if (url.endsWith('/config/preview')) return jsonResponse(PREVIEW_VALID)
      if (url.endsWith('/config/apply')) return jsonResponse({ detail: APPLY_REJECTED_DETAIL }, 422)
      return jsonResponse({})
    }),
  )

  const consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined)

  renderApp({ isAdmin: true, route: '/admin/service' })
  await screen.findByRole('navigation')
  await userEvent.click(screen.getByRole('button', { name: 'Diff anzeigen' }))
  // Scoped to the dialog: the pending banner carries an Apply of its own
  // (it opens this dialog), so the name is ambiguous page-wide.
  await userEvent.click(
    within(await screen.findByRole('dialog')).getByRole('button', { name: 'Übernehmen' }),
  )

  await waitFor(() =>
    expect(within(screen.getByRole('dialog')).getByText(/Input should be a valid integer/)).toBeInTheDocument(),
  )

  const loopMessages = consoleError.mock.calls.filter((call) =>
    call.some((arg) => typeof arg === 'string' && arg.includes('Maximum update depth exceeded')),
  )
  expect(loopMessages).toHaveLength(0)
})

it('clears the marker when the session ends', async () => {
  // A single App instance persists across sign-in -> sign-out -> sign-in
  // (that is exactly what makes the hooks-above-early-returns fix from the
  // first round necessary), so the same instance must not still be holding
  // the previous operator's issue marker once a new session starts. Driven
  // through the real sign-out/sign-in UI (rather than swapping the mocked
  // `useSession` return value and forcing an external `rerender`): a
  // `useSession` mock backed by real `useState` is a stateful hook in its
  // own right, and React 18 does not reliably pick up an externally forced
  // `rerender` of `<MemoryRouter>`'s subtree once a descendant has already
  // triggered its own state update (confirmed with a from-scratch repro
  // outside this codebase -- a `MemoryRouter`/testing-library interaction,
  // not anything specific to App). Signing out through the UI sidesteps it
  // entirely, and is arguably the more faithful test besides.
  window.localStorage.setItem('tbai_admin_draft', JSON.stringify({ port: 9999 }))
  installFetchRouter({ previewResponses: [PREVIEW_INVALID] })

  const ADMIN_A = {
    username: 'a.mueller',
    roles: ['Administrator'],
    is_admin: true,
    tb_server_url: 'https://tb:9443/api/',
  }
  const ADMIN_B = {
    username: 'b.schmidt',
    roles: ['Administrator'],
    is_admin: true,
    tb_server_url: 'https://tb:9443/api/',
  }

  function useStatefulSession() {
    const [session, setSession] = useState<typeof ADMIN_A | null>(ADMIN_A)
    return {
      session,
      loading: false,
      busy: false,
      error: null,
      signIn: async () => setSession(ADMIN_B),
      signOut: async () => setSession(null),
    }
  }
  vi.spyOn(sessionState, 'useSession').mockImplementation(useStatefulSession as never)

  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/admin/service']}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  )

  await screen.findByRole('navigation')
  await userEvent.click(screen.getByRole('button', { name: 'Diff anzeigen' }))
  expect(await screen.findByLabelText('port')).toHaveAttribute('aria-invalid', 'true')

  // The session ends -- an expired session surfaces as `session` becoming
  // null exactly like an explicit sign-out does, so this covers both.
  await userEvent.click(screen.getByRole('button', { name: 'Abmelden' }))
  await waitFor(() =>
    expect(screen.getByRole('button', { name: /anmelden/i })).toBeInTheDocument(),
  )

  // A different operator signs in on the same machine.
  await userEvent.type(screen.getByLabelText('Benutzername'), 'b.schmidt')
  await userEvent.type(screen.getByLabelText('Passwort'), 'pw')
  await userEvent.click(screen.getByRole('button', { name: 'Mit TestBench anmelden' }))

  await screen.findByRole('navigation')
  expect(screen.getByLabelText('port')).not.toHaveAttribute('aria-invalid', 'true')
})

describe('the phase 3 routes', () => {
  it('renders the Agents screen at /admin/agents', async () => {
    renderApp({ isAdmin: true, route: '/admin/agents' })
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'Agenten' })).toBeInTheDocument(),
    )
  })

  it('renders the Projects screen at /admin/projects', async () => {
    renderApp({ isAdmin: true, route: '/admin/projects' })
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'Projekte' })).toBeInTheDocument(),
    )
  })

  it('renders agent detail at /admin/agents/:agentKey', async () => {
    renderApp({ isAdmin: true, route: '/admin/agents/reviewer' })
    // The stubbed fetch answers every call with the /meta payload, so the
    // config resolves to an object with no `agents` at all and the screen
    // takes its unknown-agent branch. That branch only renders if the route
    // matched AgentDetail rather than falling through to the Status redirect.
    await waitFor(() => expect(screen.getByTestId('unknown-agent')).toBeInTheDocument())
  })

  it('keeps both screens reachable for a non-admin session', async () => {
    renderApp({ isAdmin: false, route: '/admin/agents' })
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'Agenten' })).toBeInTheDocument(),
    )
  })
})

describe('the phase 4a prompt routes', () => {
  it('renders the prompt tree at /admin/prompts', async () => {
    renderApp({ isAdmin: true, route: '/admin/prompts' })
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'Prompts' })).toBeInTheDocument(),
    )
  })

  it('renders the prompt editor at /admin/prompts/:lang/:agent', async () => {
    renderApp({ isAdmin: true, route: '/admin/prompts/de/explainer' })
    // The stubbed fetch answers every call with the /meta payload, so the
    // document query resolves to a 200 whose body has none of PromptDocument's
    // fields -- the same "malformed but truthy" shape the tree screen's own
    // guard (task 14) had to defend against. Reaching the editor's own testid
    // rather than crashing, or falling through to the Status redirect, is
    // what proves the route matched AND the field-level defaulting holds.
    await waitFor(() => expect(screen.getByTestId('prompt-editor')).toBeInTheDocument())
  })

  it('keeps the prompt editor reachable for a non-admin session', async () => {
    renderApp({ isAdmin: false, route: '/admin/prompts/de/explainer' })
    await waitFor(() => expect(screen.getByTestId('prompt-editor')).toBeInTheDocument())
  })
})
