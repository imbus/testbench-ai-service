import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
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
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[route]}>
        <App />
      </MemoryRouter>
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

test('the login screen shows the server from /meta', async () => {
  asSession(null)
  renderWithoutSession()
  await waitFor(() =>
    expect(screen.getByLabelText('TestBench-Server')).toHaveValue(
      'https://tb:9443/api/',
    ),
  )
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
