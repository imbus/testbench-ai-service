import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import type { ConfigIssue } from '../api/types'
import { de } from '../i18n/de'
// The constant, not the literal: a rename of the storage key must not leave
// these tests asserting against a key nothing writes.
import { DRAFT_STORAGE_KEY, DraftProvider } from '../state/draft'
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

function renderSection({
  section = 'service',
  isAdmin = false,
  disk = CONFIG.disk,
  running = CONFIG.running,
  issues = [],
  initialEntries = '/admin/llm',
}: {
  section?: 'service' | 'llm' | 'logging'
  isAdmin?: boolean
  disk?: Record<string, unknown>
  running?: Record<string, unknown>
  issues?: ConfigIssue[]
  /** The scope lives in the URL, so the screen needs a router around it. */
  initialEntries?: string
} = {}) {
  // If specific disk/running values are provided, update the fetch mock
  if (
    disk !== CONFIG.disk ||
    running !== CONFIG.running
  ) {
    const fetchMock = vi.mocked(fetch)
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ running, disk, config_path: '/tmp/config.toml' }),
    } as Response)
  }
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <MemoryRouter initialEntries={[initialEntries]}>
      <QueryClientProvider client={client}>
        <DraftProvider saved={disk}>
          <ConfigSection section={section} lang="de" isAdmin={isAdmin} issues={issues} />
        </DraftProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  window.localStorage.clear()
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
  renderSection({ section: 'service' })
  await waitFor(() =>
    expect(screen.getByText('https://tb.example.com:9443/api/')).toBeInTheDocument(),
  )
  expect(screen.getByText('8010')).toBeInTheDocument()
})

test('every value is read-only in phase 1', async () => {
  renderSection({ section: 'service' })
  // Positive assertion first: real values are actually on screen, so the
  // negative checks below cannot pass against a component that rendered
  // nothing at all.
  await waitFor(() => expect(screen.getByText('127.0.0.1')).toBeInTheDocument())
  expect(screen.queryAllByRole('textbox')).toHaveLength(0)
  expect(screen.queryAllByRole('checkbox')).toHaveLength(0)
  expect(screen.queryAllByRole('combobox')).toHaveLength(0)
})

test('switching tabs shows the TestBench connection fields', async () => {
  renderSection({ section: 'service' })
  await waitFor(() => expect(screen.getByText('127.0.0.1')).toBeInTheDocument())
  await userEvent.click(screen.getByRole('tab', { name: 'TestBench-Verbindung' }))
  // Assert content from the new tab actually appears, not merely that the
  // click happened.
  expect(screen.getByText('120')).toBeInTheDocument()
})

test('booleans render as true/false rather than an empty control', async () => {
  renderSection({ section: 'service' })
  await waitFor(() => expect(screen.getByText('false')).toBeInTheDocument())
})

test('an unset value renders as a dash, not "null"', async () => {
  renderSection({ section: 'service' })
  await waitFor(() => expect(screen.getByText('127.0.0.1')).toBeInTheDocument())
  expect(screen.queryByText('null')).toBeNull()
  expect(screen.getAllByText('—').length).toBeGreaterThan(0)
})

test('the llm section shows the provider', async () => {
  renderSection({ section: 'llm' })
  await waitFor(() => expect(screen.getByText('openai')).toBeInTheDocument())
})

test('the logging section shows both sinks', async () => {
  renderSection({ section: 'logging' })
  await waitFor(() => expect(screen.getByText('svc.log')).toBeInTheDocument())
  expect(screen.getByText('INFO')).toBeInTheDocument()
})

test('the config path is shown so the operator knows which file this is', async () => {
  renderSection({ section: 'service' })
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
  renderSection({ section: 'service' })
  await waitFor(() =>
    expect(screen.getByRole('alert')).toHaveTextContent(
      'Konfiguration konnte nicht geladen werden',
    ),
  )
  // The raw backend detail may still appear as secondary diagnostic text.
  expect(screen.getByRole('alert')).toHaveTextContent('boom')
})

test('renders editable fields for an admin', async () => {
  renderSection({ section: 'service', isAdmin: true })

  expect(await screen.findByLabelText('host')).toBeEnabled()
})

test('renders read-only fields for a non-admin', async () => {
  renderSection({ section: 'service', isAdmin: false })

  await screen.findByText('tb_server_url')
  expect(screen.queryByLabelText('host')).not.toBeInTheDocument()
})

test('measures edits against the disk config, not the running one', async () => {
  // The disk file omits 'debug'; the running config defaults it to false.
  // Showing 'false' is right; counting it as a pending change is not.
  renderSection({
    section: 'service',
    isAdmin: true,
    disk: { host: '127.0.0.1' },
    running: { host: '127.0.0.1', debug: false, port: 8010 },
  })

  const debug = await screen.findByRole('switch', { name: 'debug' })
  expect(debug).toHaveAttribute('aria-checked', 'false')
  expect(screen.queryByRole('button', { name: /revert/i })).not.toBeInTheDocument()
})

test('shows a field-addressed validation issue on the right field', async () => {
  renderSection({
    section: 'service',
    isAdmin: true,
    issues: [{ path: 'port', message: 'Input should be a valid integer', toml_section: '[x]' }],
  })

  expect(await screen.findByLabelText('port')).toHaveAttribute('aria-invalid', 'true')
})

test('does not show an issue addressed to a different tab', async () => {
  renderSection({
    section: 'service',
    isAdmin: true,
    issues: [
      { path: 'llm_config.model', message: 'nope', toml_section: '[x]' },
    ],
  })

  await screen.findByLabelText('host')
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})

test('shows an issue addressed to an array element on the array field', async () => {
  const message = 'Invalid path'
  renderSection({
    section: 'service',
    isAdmin: true,
    issues: [
      { path: 'prompts_dir.0', message, toml_section: '[x]' },
    ],
  })

  expect(await screen.findByLabelText('prompts_dir')).toHaveAttribute('aria-invalid', 'true')
  expect(screen.getByText(message)).toBeInTheDocument()
})

test('does not match issues on fields with similar names (dot boundary)', async () => {
  renderSection({
    section: 'service',
    isAdmin: true,
    issues: [
      { path: 'port_extra', message: 'nope', toml_section: '[x]' },
    ],
  })

  await screen.findByLabelText('port')
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})

test('marks a Service tab when its fields carry issues', async () => {
  renderSection({
    section: 'service',
    isAdmin: true,
    issues: [
      // ssl_cert is in the tls tab (3rd tab)
      { path: 'ssl_cert', message: 'SSL certificate required', toml_section: '[x]' },
    ],
  })

  // Wait for the fields to load
  await screen.findByLabelText('host')
  // The tls tab should be marked with an issue count
  const tlsTab = screen.getByRole('tab', { name: /HTTPS.*1.*issue/i })
  expect(tlsTab).toBeInTheDocument()
  // The general tab (currently selected) should not be marked
  const generalTab = screen.getByRole('tab', { name: 'Allgemein' })
  expect(generalTab).toHaveAttribute('aria-selected', 'true')
  expect(generalTab).toHaveAttribute('aria-label', 'Allgemein')
})

test('marks multiple tabs when they have issues', async () => {
  renderSection({
    section: 'service',
    isAdmin: true,
    issues: [
      { path: 'port', message: 'Invalid port', toml_section: '[x]' },
      { path: 'ssl_cert', message: 'Invalid cert', toml_section: '[x]' },
      { path: 'trusted_proxies.0', message: 'Invalid proxy', toml_section: '[x]' },
    ],
  })

  // Wait for the fields to load
  await screen.findByLabelText('host')
  // general tab has port (1 issue)
  expect(screen.getByRole('tab', { name: /Allgemein.*1.*issue/i })).toBeInTheDocument()
  // tls tab has ssl_cert (1 issue)
  expect(screen.getByRole('tab', { name: /HTTPS.*1.*issue/i })).toBeInTheDocument()
  // proxy tab has trusted_proxies (1 issue)
  expect(screen.getByRole('tab', { name: /Reverse Proxy.*1.*issue/i })).toBeInTheDocument()
})

test('does not mark tabs when there are no issues', async () => {
  renderSection({
    section: 'service',
    isAdmin: true,
    issues: [],
  })

  // Wait for the fields to load
  await screen.findByLabelText('host')
  // All tabs should have no issue markers
  const tabs = screen.getAllByRole('tab')
  tabs.forEach((tab) => {
    // Tab labels should not contain issue counts
    const label = tab.getAttribute('aria-label')
    expect(label).not.toMatch(/issue/)
  })
})

test('marks tabs with issues on non-selected array elements', async () => {
  renderSection({
    section: 'service',
    isAdmin: true,
    issues: [
      // trusted_proxies.0 should mark the proxy tab
      { path: 'trusted_proxies.0', message: 'Invalid IP', toml_section: '[x]' },
    ],
  })

  // Wait for the fields to load
  await screen.findByLabelText('host')
  const proxyTab = screen.getByRole('tab', { name: /Reverse Proxy.*1.*issue/i })
  expect(proxyTab).toBeInTheDocument()
})

// --- Per-project llm_config (phase 4d) ------------------------------------

const PROJECT_CONFIG = {
  running: {
    ...CONFIG.running,
    llm_config: { provider: 'anthropic', model: 'claude-opus-5', timeout: null },
    projects: {
      Alpha: {
        language: null,
        // As the backend really dumps it: every default filled in.
        llm_config: {
          provider: 'openai',
          auth_method: 'api_key',
          model: null,
          timeout: 12.5,
          max_retries: null,
          extra_models: {},
        },
        agents: null,
      },
    },
  },
  disk: {
    llm_config: { provider: 'anthropic', model: 'claude-opus-5' },
    projects: { Alpha: { llm_config: { timeout: 12.5 } } },
  },
  config_path: '/tmp/config.toml',
}

function renderLlm(options: { initialEntries?: string; isAdmin?: boolean } = {}) {
  return renderSection({
    section: 'llm',
    isAdmin: options.isAdmin ?? true,
    running: PROJECT_CONFIG.running,
    disk: PROJECT_CONFIG.disk,
    initialEntries: options.initialEntries ?? '/admin/llm',
  })
}

test('the LLM screen offers a tab per project that overrides llm_config', async () => {
  renderLlm()
  expect(await screen.findByRole('tab', { name: 'Alpha' })).toBeInTheDocument()
  expect(screen.getByRole('tab', { name: /global/i })).toHaveAttribute('aria-selected', 'true')
})

test('a project in the URL is the selected scope', async () => {
  renderLlm({ initialEntries: '/admin/llm?project=Alpha' })
  expect(await screen.findByRole('tab', { name: 'Alpha' })).toHaveAttribute(
    'aria-selected',
    'true',
  )
})

test('an unstated field shows the inherited global value, not a filled default', async () => {
  // The whole point. `running` reports provider="openai" for Alpha because a
  // pydantic dump fills defaults; the operator must see the anthropic they
  // actually inherit.
  //
  // Asserted on the control rather than with getByText(/anthropic/): the
  // provider select always renders an <option>anthropic</option>, so a text
  // query matches both that and the inherit note and resolves to neither.
  renderLlm({ initialEntries: '/admin/llm?project=Alpha' })
  await screen.findByRole('tab', { name: 'Alpha' })
  expect(screen.getByLabelText('provider')).toHaveValue('anthropic')
})

test('a stated field shows the project value', async () => {
  renderLlm({ initialEntries: '/admin/llm?project=Alpha' })
  await screen.findByRole('tab', { name: 'Alpha' })
  expect(screen.getByDisplayValue('12.5')).toBeInTheDocument()
})

test('a non-admin sees the inherited value too, not the filled default', async () => {
  // The read-only path reads the same two sources in the same order. Reading
  // `running` here would show provider="openai" on a project that inherits
  // anthropic -- the exact misreport this screen exists to avoid, and a
  // non-admin has no control to notice it is wrong on.
  renderLlm({ initialEntries: '/admin/llm?project=Alpha', isAdmin: false })
  await screen.findByRole('tab', { name: 'Alpha' })
  expect(screen.getByText('anthropic')).toBeInTheDocument()
  expect(screen.queryByText('openai')).not.toBeInTheDocument()
})

test('editing in project scope writes the project path, not the global one', async () => {
  renderLlm({ initialEntries: '/admin/llm?project=Alpha' })
  await screen.findByRole('tab', { name: 'Alpha' })

  const model = screen.getByLabelText(/model/i)
  await userEvent.type(model, 'gpt-5')

  await waitFor(() =>
    expect(
      JSON.parse(window.localStorage.getItem(DRAFT_STORAGE_KEY) ?? '{}'),
    ).toHaveProperty(['projects.Alpha.llm_config.model']),
  )
})

test('selecting a project scope queues no edit', async () => {
  // Choosing a scope is navigation, never an edit: an empty override table
  // would appear in the diff the operator never asked for.
  renderLlm()
  await userEvent.click(await screen.findByRole('tab', { name: 'Alpha' }))
  // Wait for the scope to have actually switched before reading the draft, so
  // an empty result cannot just mean "nothing has happened yet".
  await waitFor(() =>
    expect(screen.getByRole('tab', { name: 'Alpha' })).toHaveAttribute('aria-selected', 'true'),
  )
  expect(JSON.parse(window.localStorage.getItem(DRAFT_STORAGE_KEY) ?? '{}')).toEqual({})
})

test('the model table is global-only', async () => {
  // ModelTable renders no testid; its <h3>{t.models}</h3> heading is what
  // identifies it, and this suite renders in German.
  renderLlm()
  expect(await screen.findByRole('heading', { name: de.models })).toBeInTheDocument()

  await userEvent.click(screen.getByRole('tab', { name: 'Alpha' }))
  await waitFor(() =>
    expect(screen.queryByRole('heading', { name: de.models })).not.toBeInTheDocument(),
  )
})

test('a validation issue on a project field lands on that field', async () => {
  renderSection({
    section: 'llm',
    isAdmin: true,
    running: PROJECT_CONFIG.running,
    disk: PROJECT_CONFIG.disk,
    initialEntries: '/admin/llm?project=Alpha',
    issues: [
      {
        path: 'projects.Alpha.llm_config.provider',
        message: 'not a valid provider',
        toml_section: '[testbench-ai-service.projects.Alpha.llm_config]',
      },
    ],
  })
  expect(await screen.findByText('not a valid provider')).toBeInTheDocument()
})
