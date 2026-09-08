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

const renderApp = () => {
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
  renderApp()
  await waitFor(() =>
    expect(screen.getByRole('button', { name: /anmelden/i })).toBeInTheDocument(),
  )
})

test('shows the shell when signed in', async () => {
  asSession({
    username: 'a.mueller',
    roles: ['Administrator'],
    is_admin: true,
    tb_server_url: 'https://tb.example.com:9443/api/',
  })
  renderApp()
  await waitFor(() => expect(screen.getByRole('navigation')).toBeInTheDocument())
  expect(screen.getByText('a.mueller')).toBeInTheDocument()
})

test('shows a read-only notice to a non-admin', async () => {
  asSession({
    username: 'p.user',
    roles: ['ProjectUser'],
    is_admin: false,
    tb_server_url: 'https://tb.example.com:9443/api/',
  })
  renderApp()
  await waitFor(() =>
    expect(screen.getByText(/nur lesend/i)).toBeInTheDocument(),
  )
})

test('renders nothing decisive while the session is still loading', () => {
  asSession(null, true)
  renderApp()
  expect(screen.queryByRole('button', { name: /anmelden/i })).toBeNull()
})

test('the login screen shows the server from /meta', async () => {
  asSession(null)
  renderApp()
  await waitFor(() =>
    expect(screen.getByLabelText('TestBench-Server')).toHaveValue(
      'https://tb:9443/api/',
    ),
  )
})
