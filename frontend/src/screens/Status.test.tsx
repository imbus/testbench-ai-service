import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { formatActivityTime, Status } from './Status'
import type { ActivityEntry, StatusResponse } from '../api/types'

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
  in_flight_tasks: 0,
  restart_required: [],
  token_usage: { available: true, models: [] },
}

const ACTIVITY: ActivityEntry[] = [
  {
    timestamp: '2026-10-13T10:12:03.000+00:00',
    level: 'ERROR',
    source: 'testbench_ai_service',
    message: 'Agent failed',
    scope: 'user',
    agent: 'test_case_set_reviewer',
    project_key: 'p-1',
    run_id: 'r1',
    exc: 'Traceback (most recent call last):\nValueError: boom',
  },
  {
    timestamp: '2026-10-13T10:11:51.000+00:00',
    level: 'INFO',
    source: 'testbench_ai_service',
    message: 'Agent started',
    scope: 'user',
    agent: 'test_case_set_reviewer',
    project_key: 'p-1',
    run_id: 'r1',
    exc: null,
  },
  {
    timestamp: '2026-10-13T09:00:00.000+00:00',
    level: 'INFO',
    source: 'uvicorn.error',
    message: 'Application startup complete.',
    scope: 'service',
    agent: null,
    project_key: null,
    run_id: null,
    exc: null,
  },
]

function renderStatus({ isAdmin = true }: { isAdmin?: boolean } = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <Status isAdmin={isAdmin} />
    </QueryClientProvider>,
  )
}

const fetchMock = vi.fn((url: string) =>
  Promise.resolve(
    new Response(JSON.stringify(url.includes('/activity') ? ACTIVITY : STATUS), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }),
  ),
)

beforeEach(() => {
  fetchMock.mockClear()
  vi.stubGlobal('fetch', fetchMock)
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

test('renders activity newest first, grouped by run', async () => {
  renderStatus()
  await waitFor(() => expect(screen.getByText('Agent failed')).toBeInTheDocument())
  const rows = screen.getAllByTestId('activity-line')
  expect(rows[0]).toHaveTextContent('ERROR')
  expect(screen.getAllByTestId('run-header')).toHaveLength(1)
  expect(screen.getByText('test_case_set_reviewer · p-1')).toBeInTheDocument()
})

test('keeps a traceback with its entry', async () => {
  renderStatus()
  await waitFor(() => expect(screen.getByText('Agent failed')).toBeInTheDocument())
  expect(screen.getByText(/ValueError: boom/)).toBeInTheDocument()
})

test('badges service entries', async () => {
  renderStatus()
  await waitFor(() =>
    expect(screen.getByText('Application startup complete.')).toBeInTheDocument(),
  )
  expect(screen.getByTestId('service-badge')).toBeInTheDocument()
})

test('admins can switch scope', async () => {
  renderStatus({ isAdmin: true })
  await waitFor(() => expect(screen.getByRole('button', { name: 'Service' })).toBeInTheDocument())
  fireEvent.click(screen.getByRole('button', { name: 'Service' }))
  await waitFor(() =>
    expect(fetchMock.mock.calls.some(([u]) => String(u).includes('scope=service'))).toBe(true),
  )
})

test('non-admins get no scope switch and no log file path', async () => {
  renderStatus({ isAdmin: false })
  await waitFor(() => expect(screen.getByText('Meine Aktivität')).toBeInTheDocument())
  expect(screen.queryByRole('button', { name: 'Service' })).not.toBeInTheDocument()
  expect(fetchMock.mock.calls.every(([u]) => !String(u).includes('scope=service'))).toBe(true)
  expect(screen.queryByText(/\.log$/)).not.toBeInTheDocument()
})

test('reports an unreachable TestBench and still renders the rest of the screen', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) =>
      Promise.resolve(
        new Response(
          JSON.stringify(
            url.includes('/activity')
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

describe('formatActivityTime', () => {
  const now = new Date('2026-10-13T15:00:00Z')

  test('shows only the local time for an entry from today', () => {
    expect(formatActivityTime('2026-10-13T10:12:03.000+00:00', now, 'de-DE', 'Europe/Berlin')).toBe(
      '12:12:03',
    )
  })

  test('decides "today" in the local time zone, not in UTC', () => {
    // 22:30 UTC on the 12th is 00:30 on the 13th in Berlin.
    expect(formatActivityTime('2026-10-12T22:30:00.000+00:00', now, 'de-DE', 'Europe/Berlin')).toBe(
      '00:30:00',
    )
  })

  test('adds a short local date for an older entry', () => {
    expect(formatActivityTime('2026-10-12T10:12:03.000+00:00', now, 'de-DE', 'Europe/Berlin')).toBe(
      '12.10.26, 12:12:03',
    )
    expect(formatActivityTime('2026-10-12T10:12:03.000+00:00', now, 'en-GB', 'UTC')).toBe(
      '12/10/26, 10:12:03',
    )
  })
})

describe('token usage', () => {
  function stubStatus(tokenUsage: StatusResponse['token_usage']) {
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) =>
        Promise.resolve(
          new Response(
            JSON.stringify(url.includes('/activity') ? [] : { ...STATUS, token_usage: tokenUsage }),
            { status: 200, headers: { 'Content-Type': 'application/json' } },
          ),
        ),
      ),
    )
  }

  const entry = (model: string, input: number, output: number) => ({
    provider: 'openai',
    model,
    calls: 3,
    input_tokens: input,
    output_tokens: output,
    reasoning_tokens: 100,
    last_used: '2026-10-20T09:00:00+00:00',
  })

  test('sums all models and lists each one', async () => {
    stubStatus({ available: true, models: [entry('gpt-5', 12000, 3000), entry('o3', 500, 250)] })
    renderStatus()

    await waitFor(() =>
      expect(screen.getByTestId('token-total')).toHaveTextContent('12.500 Eingabe-Tokens / 3.250 Ausgabe-Tokens'),
    )
    expect(screen.getByText('gpt-5')).toBeInTheDocument()
    expect(screen.getByText('o3')).toBeInTheDocument()
    expect(screen.getByText('12.000')).toBeInTheDocument()
  })

  test('says so when nothing has been counted yet', async () => {
    stubStatus({ available: true, models: [] })
    renderStatus()
    expect(await screen.findByText(/noch keine llm-aufrufe/i)).toBeInTheDocument()
  })

  test('says so when the usage file cannot be read, rather than showing zero', async () => {
    stubStatus({ available: false, models: [] })
    renderStatus()
    expect(await screen.findByText(/nicht gelesen werden/i)).toBeInTheDocument()
    expect(screen.queryByTestId('token-total')).not.toBeInTheDocument()
  })
})
