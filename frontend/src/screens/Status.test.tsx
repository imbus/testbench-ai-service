import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Status } from './Status'
import type { LogLine, StatusResponse } from '../api/types'

const STATUS: StatusResponse = {
  service: {
    version: '1.0.1',
    host: '127.0.0.1',
    port: 8010,
    debug: false,
    uptime_seconds: 8040,
    language: 'de',
  },
  testbench: { url: 'https://tb.example.com:9443/api/', reachable: true, detail: 'HTTP 401' },
  api_keys: [
    { name: 'OPENAI_API_KEY', present: true },
    { name: 'ANTHROPIC_API_KEY', present: false },
  ],
  agents: { total: 3, enabled: 2, project_overrides: 4, projects: 2 },
  log_file: 'testbench-ai-service.log',
}

const LOGS: LogLine[] = [
  {
    raw: 'x',
    timestamp: '2026-09-08 10:12:03',
    level: 'ERROR',
    source: 'testbench.client',
    message: 'GET /projects failed',
  },
  {
    raw: 'y',
    timestamp: '2026-09-08 10:11:51',
    level: 'INFO',
    source: 'auth',
    message: 'token validated',
  },
]

function renderStatus() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <Status lang="de" />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) =>
      Promise.resolve(
        new Response(JSON.stringify(url.includes('/logs') ? LOGS : STATUS), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    ),
  )
})

afterEach(() => vi.restoreAllMocks())

test('shows the service card', async () => {
  renderStatus()
  await waitFor(() => expect(screen.getByText(/127\.0\.0\.1:8010/)).toBeInTheDocument())
  expect(screen.getByText(/1\.0\.1/)).toBeInTheDocument()
})

test('formats uptime readably', async () => {
  renderStatus()
  await waitFor(() => expect(screen.getByText(/2h 14m/)).toBeInTheDocument())
})

test('shows the TestBench url and connected state', async () => {
  renderStatus()
  await waitFor(() =>
    expect(screen.getByText('https://tb.example.com:9443/api/')).toBeInTheDocument(),
  )
  expect(screen.getByText('Verbunden')).toBeInTheDocument()
})

test('lists api keys by presence, never a value', async () => {
  renderStatus()
  await waitFor(() => expect(screen.getByText('OPENAI_API_KEY')).toBeInTheDocument())
  expect(screen.getByText('ANTHROPIC_API_KEY')).toBeInTheDocument()
  // The backend only ever reports presence, never a value — the DOM must not
  // contain anything that looks like a credential (e.g. "sk-..." style tokens).
  expect(screen.queryByText(/sk-[A-Za-z0-9]/)).not.toBeInTheDocument()
  expect(document.body.textContent).not.toMatch(/sk-[A-Za-z0-9]{10,}/)
})

test('summarises agents and overrides', async () => {
  renderStatus()
  await waitFor(() => expect(screen.getByText(/2 aktiv/)).toBeInTheDocument())
  expect(screen.getByText(/4 Überschreibungen/)).toBeInTheDocument()
})

test('renders recent log lines newest first', async () => {
  renderStatus()
  await waitFor(() => expect(screen.getByText('GET /projects failed')).toBeInTheDocument())
  const rows = screen.getAllByTestId('log-line')
  expect(rows[0]).toHaveTextContent('ERROR')
})

test('reports an unreachable TestBench and still renders the rest of the screen', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) =>
      Promise.resolve(
        new Response(
          JSON.stringify(
            url.includes('/logs')
              ? []
              : { ...STATUS, testbench: { ...STATUS.testbench, reachable: false } },
          ),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ),
      ),
    ),
  )
  renderStatus()
  await waitFor(() => expect(screen.getByTestId('tb-state')).toHaveTextContent(/nicht/i))
  // A 200 response with reachable: false is not an error state — the rest of
  // the screen (service card, api keys, agents) must still be present, and no
  // error/alert should be rendered instead of the dashboard.
  expect(screen.getByText(/127\.0\.0\.1:8010/)).toBeInTheDocument()
  expect(screen.getByText('OPENAI_API_KEY')).toBeInTheDocument()
  expect(screen.getByText(/2 aktiv/)).toBeInTheDocument()
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})

test('shows a translated error when the status request fails', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(() =>
      Promise.resolve(
        new Response(JSON.stringify({ detail: 'boom' }), {
          status: 500,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    ),
  )
  renderStatus()
  // The primary alert text must be the translated fallback, not the raw
  // (English, backend-shaped) error detail — this pins the statusError key
  // rather than merely asserting an alert exists.
  await waitFor(() =>
    expect(screen.getByRole('alert')).toHaveTextContent('Status konnte nicht geladen werden'),
  )
  // The raw backend detail may still appear as secondary diagnostic text.
  expect(screen.getByRole('alert')).toHaveTextContent('boom')
})
