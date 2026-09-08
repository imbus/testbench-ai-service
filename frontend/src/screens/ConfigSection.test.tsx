import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ConfigSection } from './ConfigSection'

// Correction 1: the brief's fixture included `in_sync: true`. The backend
// model and ConfigResponse (src/api/types.ts) carry no such field — only
// running, disk and config_path — so it is omitted here rather than
// asserting behavior against a field the server never sends.
const CONFIG = {
  running: {
    tb_server_url: 'https://tb.example.com:9443/api/',
    host: '127.0.0.1',
    port: 8010,
    debug: false,
    language: 'de',
    prompts_dir: 'prompts',
    templates_dir: null,
    tb_ssl_verify: true,
    tb_ssl_ca_bundle: null,
    tb_connect_timeout: 10.0,
    tb_read_timeout: 120.0,
    tb_max_retries: 3,
    ssl_cert: null,
    ssl_key: null,
    ssl_ca_cert: null,
    trusted_proxies: [],
    llm_config: { provider: 'openai', model: null },
    logging: {
      console: { log_level: 'INFO', log_format: '%(levelname)s: %(message)s' },
      file: { file_name: 'svc.log', log_level: 'DEBUG', log_format: '%(message)s' },
    },
  },
  disk: {},
  config_path: 'C:\\svc\\config.toml',
}

function renderSection(section: 'service' | 'llm' | 'logging') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ConfigSection section={section} lang="de" />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn(() =>
      Promise.resolve(
        new Response(JSON.stringify(CONFIG), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    ),
  )
})

afterEach(() => vi.restoreAllMocks())

test('shows service values from the running config', async () => {
  renderSection('service')
  await waitFor(() =>
    expect(screen.getByText('https://tb.example.com:9443/api/')).toBeInTheDocument(),
  )
  expect(screen.getByText('8010')).toBeInTheDocument()
})

test('every value is read-only in phase 1', async () => {
  renderSection('service')
  // Positive assertion first: real values are actually on screen, so the
  // negative checks below cannot pass against a component that rendered
  // nothing at all.
  await waitFor(() => expect(screen.getByText('127.0.0.1')).toBeInTheDocument())
  expect(screen.queryAllByRole('textbox')).toHaveLength(0)
  expect(screen.queryAllByRole('checkbox')).toHaveLength(0)
  expect(screen.queryAllByRole('combobox')).toHaveLength(0)
})

test('switching tabs shows the TestBench connection fields', async () => {
  renderSection('service')
  await waitFor(() => expect(screen.getByText('127.0.0.1')).toBeInTheDocument())
  await userEvent.click(screen.getByRole('tab', { name: 'TestBench-Verbindung' }))
  // Assert content from the new tab actually appears, not merely that the
  // click happened.
  expect(screen.getByText('120')).toBeInTheDocument()
})

test('booleans render as true/false rather than an empty control', async () => {
  renderSection('service')
  await waitFor(() => expect(screen.getByText('false')).toBeInTheDocument())
})

test('an unset value renders as a dash, not "null"', async () => {
  renderSection('service')
  await waitFor(() => expect(screen.getByText('127.0.0.1')).toBeInTheDocument())
  expect(screen.queryByText('null')).toBeNull()
  expect(screen.getAllByText('—').length).toBeGreaterThan(0)
})

test('the llm section shows the provider', async () => {
  renderSection('llm')
  await waitFor(() => expect(screen.getByText('openai')).toBeInTheDocument())
})

test('the logging section shows both sinks', async () => {
  renderSection('logging')
  await waitFor(() => expect(screen.getByText('svc.log')).toBeInTheDocument())
  expect(screen.getByText('INFO')).toBeInTheDocument()
})

test('the config path is shown so the operator knows which file this is', async () => {
  renderSection('service')
  await waitFor(() =>
    expect(screen.getByText(/config\.toml/)).toBeInTheDocument(),
  )
})

// Correction 2: mirrors Status.test.tsx's "shows a translated error" test.
// The translated line must be the primary alert text — never the raw,
// often-English backend detail — so a German operator never sees English
// error copy as the headline.
test('shows a translated error when the config request fails', async () => {
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
  renderSection('service')
  await waitFor(() =>
    expect(screen.getByRole('alert')).toHaveTextContent(
      'Konfiguration konnte nicht geladen werden',
    ),
  )
  // The raw backend detail may still appear as secondary diagnostic text.
  expect(screen.getByRole('alert')).toHaveTextContent('boom')
})
