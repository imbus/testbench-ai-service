/**
 * The agent detail screen: scope switching, and a form typed by the prompt's
 * own variable declarations (design §5.4).
 */
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { DraftProvider, useDraft } from '../state/draft'
import type { ConfigResponse, ProjectsResponse, PromptForkResponse, PromptMeta } from '../api/types'
import { AgentDetail } from './AgentDetail'

// `useNavigate` is mocked rather than asserted through a real route match: the
// fork dialog's whole point is that it navigates using the SERVER's response
// fields, not a client-computed guess, and a mock spy is the direct way to
// assert what URL it was actually called with. `vi.hoisted` is required
// because `vi.mock` factories run before this module's own `const`s do.
const { navigateMock } = vi.hoisted(() => ({ navigateMock: vi.fn() }))
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>()
  return { ...actual, useNavigate: () => navigateMock }
})

const DISK = {
  language: 'de',
  agents: {
    reviewer: {
      enabled: true,
      endpoint_path: '/test-case-set-reviews',
      class_path: 'a.b.Reviewer',
      prompt: { file: 'reviewer/prompt.yaml', variant: 'Thorough', vars: { tone: 'formal' } },
    },
  },
  projects: {
    Alpha: { language: 'en', agents: { reviewer: { enabled: false } } },
    'Release 2.0': { agents: { reviewer: { prompt: { variant: 'Quick' } } } },
  },
}

const CONFIG: ConfigResponse = { running: DISK, disk: DISK, config_path: 'C:/svc/config.toml' }

const PROJECTS: ProjectsResponse = {
  projects: [
    { name: 'Alpha', key: '11' },
    { name: 'Release 2.0', key: '12' },
    { name: 'Untouched', key: '13' },
    { name: 'Car Configurator', key: '14' },
  ],
  fetched_at: '2026-09-10T08:00:00Z',
  source: 'testbench',
  error: null,
}

// The server names the fork's new directory -- it slugifies the project,
// dedupes, and may accept an operator override -- so this deliberately does
// NOT look like any name the client could compute from agentKey ('reviewer')
// or the project ('Car Configurator'). That mismatch is exactly what proves
// the navigation test reads the response instead of guessing.
const FORK_RESPONSE: PromptForkResponse = {
  lang: 'de',
  agent: 'explainer__car-configurator',
  file: 'explainer__car-configurator/prompt.yaml',
  created: ['explainer__car-configurator/prompt.yaml'],
  config_backup: 'config.toml.bak',
  reloaded: true,
  reload_detail: null,
}

const META: PromptMeta = {
  name: 'Test Case Set Reviewer',
  summary: 'Reviews a set',
  description: null,
  default_model: 'gpt-5.5',
  default_variant: 'Thorough',
  variants: [
    {
      name: 'Thorough',
      description: 'The careful one',
      model: 'gpt-5.5',
      vars: {
        max_findings: {
          name: 'Maximum findings',
          description: 'How many to report',
          value_type: 'number',
          choices: null,
          default_value: 10,
          required: false,
        },
        tone: {
          name: 'Tone',
          description: null,
          value_type: 'enum',
          choices: ['formal', 'casual'],
          default_value: null,
          required: true,
        },
        verbose: {
          name: 'Verbose',
          description: null,
          value_type: 'boolean',
          choices: null,
          default_value: null,
          required: false,
        },
        preamble: {
          name: 'Preamble',
          description: null,
          value_type: 'text',
          choices: null,
          default_value: null,
          required: false,
        },
        label: {
          name: 'Label',
          description: null,
          value_type: 'string',
          choices: null,
          default_value: null,
          required: false,
        },
      },
    },
    { name: 'Quick', description: null, model: null, vars: {} },
  ],
}

let fetchMock: ReturnType<typeof vi.fn>
let metaBody: PromptMeta | null
/** Set by a test to make the fork POST 400 instead of succeeding. */
let forkError: string | null

beforeEach(() => {
  window.localStorage.clear()
  metaBody = META
  forkError = null
  navigateMock.mockClear()
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url.startsWith('/admin/api/config')) return ok(CONFIG)
    if (url.startsWith('/admin/api/projects')) return ok(PROJECTS)
    if ((init?.method ?? 'GET').toUpperCase() === 'POST' && url.includes('/fork')) {
      return forkError
        ? ({ ok: false, status: 400, json: async () => ({ detail: forkError }) } as Response)
        : ok(FORK_RESPONSE)
    }
    if (url.includes('/prompts/')) {
      return metaBody
        ? ok(metaBody)
        : ({ ok: false, status: 404, json: async () => ({ detail: 'gone' }) } as Response)
    }
    return { ok: false, status: 404, json: async () => ({ detail: 'no' }) } as Response
  })
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

function ok(body: unknown) {
  return { ok: true, status: 200, json: async () => body } as Response
}

function Edits() {
  const draft = useDraft()
  return <span data-testid="edits">{JSON.stringify(draft.edits)}</span>
}

function edits(): Record<string, unknown> {
  return JSON.parse(screen.getByTestId('edits').textContent ?? '{}')
}

function renderDetail({
  agentKey = 'reviewer',
  isAdmin = true,
}: { agentKey?: string; isAdmin?: boolean } = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[`/admin/agents/${encodeURIComponent(agentKey)}`]}>
        <DraftProvider saved={DISK}>
          <Routes>
            <Route
              path="/admin/agents/:agentKey"
              element={<AgentDetail lang="en" isAdmin={isAdmin} issues={[]} />}
            />
          </Routes>
          <Edits />
        </DraftProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

async function ready() {
  await waitFor(() => expect(screen.getByTestId('agent-detail')).toBeInTheDocument())
}

/**
 * `renderDetail` plus the setup the fork tests need: a settled scope (global,
 * or a named project reached through the add-override picker -- exactly the
 * path an operator takes, and one that writes no edit by itself, per "switches
 * to a newly picked project without writing anything yet" above) and,
 * optionally, one queued edit so `draft.changeCount` is nonzero.
 */
async function renderAgentDetail({
  agentKey = 'reviewer',
  isAdmin = true,
  project = null,
  dirty = false,
}: {
  agentKey?: string
  isAdmin?: boolean
  project?: string | null
  dirty?: boolean
} = {}) {
  renderDetail({ agentKey, isAdmin })
  await ready()
  if (project) {
    await userEvent.selectOptions(screen.getByLabelText('Add a project override'), project)
  }
  if (dirty) {
    await userEvent.click(screen.getByRole('switch', { name: 'enabled' }))
  }
  return { navigate: navigateMock }
}

// --- header and scope switching ----------------------------------------

describe('the scope switcher', () => {
  it('starts in global scope', async () => {
    renderDetail()
    await ready()
    expect(screen.getByRole('tab', { name: 'Global' })).toHaveAttribute('aria-selected', 'true')
  })

  it('offers a tab for each project that already overrides this agent', async () => {
    renderDetail()
    await ready()
    expect(screen.getByRole('tab', { name: 'Alpha' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Release 2.0' })).toBeInTheDocument()
  })

  it('does not offer a tab for a project with no override yet', async () => {
    // It is reachable through "add a project override", but it does not
    // deserve a tab: there is nothing there to look at.
    renderDetail()
    await ready()
    expect(screen.queryByRole('tab', { name: 'Untouched' })).not.toBeInTheDocument()
  })

  it('offers the projects with no override yet in the add-override picker', async () => {
    renderDetail()
    await ready()
    const picker = screen.getByLabelText('Add a project override')
    expect(within(picker).getByRole('option', { name: 'Untouched' })).toBeInTheDocument()
    expect(within(picker).queryByRole('option', { name: 'Alpha' })).not.toBeInTheDocument()
  })

  it('switches to a project scope when its tab is chosen', async () => {
    renderDetail()
    await ready()
    await userEvent.click(screen.getByRole('tab', { name: 'Alpha' }))
    expect(screen.getByRole('tab', { name: 'Alpha' })).toHaveAttribute('aria-selected', 'true')
  })

  it('switches to a newly picked project without writing anything yet', async () => {
    // Choosing a scope is navigation, not an edit: writing an empty override
    // table on selection would put a change in the diff the operator never
    // asked for.
    renderDetail()
    await ready()
    await userEvent.selectOptions(screen.getByLabelText('Add a project override'), 'Untouched')
    expect(screen.getByRole('tab', { name: 'Untouched' })).toHaveAttribute(
      'aria-selected',
      'true',
    )
    expect(edits()).toEqual({})
  })
})

// --- the form ----------------------------------------------------------

describe('the form in global scope', () => {
  it('edits enabled against the global path', async () => {
    renderDetail()
    await ready()
    await userEvent.click(screen.getByRole('switch', { name: 'enabled' }))
    expect(edits()).toEqual({ 'agents.reviewer.enabled': false })
  })

  it('shows no inherit note on the agent settings — global inherits from nothing', async () => {
    // Scoped to the settings block on purpose. A prompt *variable* does
    // inherit globally -- from the prompt YAML's own `default_value` -- so the
    // note is correct there and is asserted separately below.
    renderDetail()
    await ready()
    const settings = screen.getByTestId('agent-settings')
    expect(within(settings).queryByTestId('inherit-note')).not.toBeInTheDocument()
  })

  it('says an unset prompt variable falls back to the prompt default', async () => {
    renderDetail()
    await ready()
    const row = screen
      .getByLabelText('Maximum findings')
      .closest('[data-testid="field-row"]') as HTMLElement
    expect(within(row).getByTestId('inherit-note').textContent).toMatch(/prompt default/i)
    expect(within(row).getByTestId('inherit-note').textContent).toMatch(/10/)
  })

  it('offers the prompt variants as a select', async () => {
    renderDetail()
    await ready()
    const select = screen.getByLabelText('variant')
    expect(within(select).getByRole('option', { name: 'Thorough' })).toBeInTheDocument()
    expect(within(select).getByRole('option', { name: 'Quick' })).toBeInTheDocument()
  })

  it('renders endpoint_path and class_path read-only, with the restart note', async () => {
    renderDetail()
    await ready()
    const readOnly = screen.getByTestId('agent-readonly')
    expect(within(readOnly).getByText('/test-case-set-reviews')).toBeInTheDocument()
    expect(within(readOnly).getByText('a.b.Reviewer')).toBeInTheDocument()
    expect(readOnly.textContent).toMatch(/restart/i)
  })

  it('gives endpoint_path and class_path no input at all', async () => {
    renderDetail()
    await ready()
    const readOnly = screen.getByTestId('agent-readonly')
    expect(within(readOnly).queryByRole('textbox')).not.toBeInTheDocument()
  })
})

// --- prompt variables --------------------------------------------------

describe('prompt variables', () => {
  it('renders one control per declared value_type', async () => {
    renderDetail()
    await ready()
    const vars = screen.getByTestId('agent-vars')
    // number, enum, boolean, text, string
    expect(within(vars).getByLabelText('Maximum findings')).toHaveAttribute('type', 'number')
    expect(within(vars).getByLabelText('Tone').tagName).toBe('SELECT')
    expect(within(vars).getByRole('switch', { name: 'Verbose' })).toBeInTheDocument()
    expect(within(vars).getByLabelText('Preamble').tagName).toBe('TEXTAREA')
    expect(within(vars).getByLabelText('Label')).toHaveAttribute('type', 'text')
  })

  it('labels each variable with the name the prompt author gave it', async () => {
    renderDetail()
    await ready()
    expect(screen.getByText('How many to report')).toBeInTheDocument()
  })

  it('offers an enum variable only its declared choices', async () => {
    renderDetail()
    await ready()
    const tone = screen.getByLabelText('Tone')
    expect(within(tone).getByRole('option', { name: 'formal' })).toBeInTheDocument()
    expect(within(tone).getByRole('option', { name: 'casual' })).toBeInTheDocument()
  })

  it('writes a variable to the prompt vars path', async () => {
    renderDetail()
    await ready()
    await userEvent.type(screen.getByLabelText('Maximum findings'), '5')
    expect(edits()).toEqual({ 'agents.reviewer.prompt.vars.max_findings': 5 })
  })

  it('lists the variables of the SELECTED variant, not the default one', async () => {
    // `Quick` declares none. Showing `Thorough`'s variables against it would
    // offer the operator variables the prompt will ignore.
    renderDetail()
    await ready()
    await userEvent.selectOptions(screen.getByLabelText('variant'), 'Quick')
    expect(screen.queryByLabelText('Maximum findings')).not.toBeInTheDocument()
  })

  it('still shows a configured variable the selected variant does not declare, flagged', async () => {
    // `tone` is set in config but `Quick` declares nothing. Hiding it would
    // leave a value in the file that the operator cannot see or remove.
    renderDetail()
    await ready()
    await userEvent.selectOptions(screen.getByLabelText('variant'), 'Quick')

    const undeclared = screen.getByTestId('undeclared-tone')
    expect(undeclared).toBeInTheDocument()
    expect(undeclared.textContent).toMatch(/not declared/i)
  })

  it('says so when the prompt metadata cannot be read', async () => {
    metaBody = null
    renderDetail()
    await ready()
    expect(screen.getByTestId('meta-unavailable')).toBeInTheDocument()
  })

  it('leaves the variant editable as free text when metadata is unavailable', async () => {
    metaBody = null
    renderDetail()
    await ready()
    // The operator has to be able to fix the prompt path that caused the 404.
    expect(screen.getByLabelText('variant').tagName).toBe('INPUT')
  })
})

// --- project scope ------------------------------------------------------

describe('the form in project scope', () => {
  async function inAlpha() {
    renderDetail()
    await ready()
    await userEvent.click(screen.getByRole('tab', { name: 'Alpha' }))
  }

  it('writes to the project override path', async () => {
    await inAlpha()
    await userEvent.click(screen.getByRole('switch', { name: 'enabled' }))
    // Saved override is false, so one click sets true.
    expect(edits()).toEqual({ 'projects.Alpha.agents.reviewer.enabled': true })
  })

  it('marks an un-overridden setting as inherited from global', async () => {
    await inAlpha()
    const row = screen.getByLabelText('variant').closest('[data-testid="field-row"]')
    expect(row).toHaveAttribute('data-overridden', 'false')
  })

  it('names the inherited value in the note', async () => {
    await inAlpha()
    expect(screen.getAllByTestId('inherit-note')[0].textContent).toMatch(/Inherited/)
  })

  it('reads prompt metadata in the project’s own language', async () => {
    // Alpha overrides `language = "en"`, so its prompt files live under
    // prompts_dir/en/. Reading `de` would show the wrong variants entirely.
    await inAlpha()
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some((call) => String(call[0]).includes('/prompts/en/reviewer/')),
      ).toBe(true),
    )
  })

  it('uses the global language for a project that does not override it', async () => {
    renderDetail()
    await ready()
    await userEvent.click(screen.getByRole('tab', { name: 'Release 2.0' }))
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some((call) => String(call[0]).includes('/prompts/de/reviewer/')),
      ).toBe(true),
    )
  })

  it('offers "remove all overrides" for this project', async () => {
    await inAlpha()
    await userEvent.click(screen.getByRole('button', { name: /remove all overrides/i }))
    // One null on the whole agent-override table: the server reads it as
    // "delete the key", which is exactly "this project inherits everything".
    expect(edits()).toEqual({ 'projects.Alpha.agents.reviewer': null })
  })

  it('keeps endpoint_path pointing at the global table', async () => {
    // A per-project endpoint_path would be a value that never takes effect:
    // the router table is built once at startup from the global agents.
    await inAlpha()
    const readOnly = screen.getByTestId('agent-readonly')
    expect(within(readOnly).getByText('/test-case-set-reviews')).toBeInTheDocument()
  })
})

// --- unknown agent ------------------------------------------------------

describe('an agent key that does not exist', () => {
  it('says so rather than rendering an empty form', async () => {
    renderDetail({ agentKey: 'no_such_agent' })
    await waitFor(() => expect(screen.getByTestId('unknown-agent')).toBeInTheDocument())
  })
})

// --- read-only sessions -------------------------------------------------

describe('a non-admin session', () => {
  it('renders every setting read-only', async () => {
    renderDetail({ isAdmin: false })
    await ready()
    expect(screen.queryByRole('switch')).not.toBeInTheDocument()
    expect(screen.getByTestId('agent-detail').textContent).toContain('/test-case-set-reviews')
  })
})

// --- vars inherit the way the runtime merges them ------------------------

describe('prompt variables in a project that declares its own', () => {
  /** merge_prompt_configs replaces `vars` wholesale; it does not merge keys. */
  const RUNNING = {
    ...DISK,
    projects: {
      ...DISK.projects,
      Beta: { agents: { reviewer: { prompt: { vars: { max_findings: 3 } } } } },
    },
  }

  function renderWithBeta() {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    fetchMock.mockImplementation(async (url: string) => {
      if (url.startsWith('/admin/api/config'))
        return ok({ running: RUNNING, disk: RUNNING, config_path: 'C:/svc/config.toml' })
      if (url.startsWith('/admin/api/projects')) return ok(PROJECTS)
      if (url.includes('/prompts/')) return ok(META)
      return { ok: false, status: 404, json: async () => ({ detail: 'no' }) } as Response
    })
    return render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/admin/agents/reviewer']}>
          <DraftProvider saved={RUNNING}>
            <Routes>
              <Route
                path="/admin/agents/:agentKey"
                element={<AgentDetail lang="en" isAdmin issues={[]} />}
              />
            </Routes>
            <Edits />
          </DraftProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    )
  }

  async function inBeta() {
    renderWithBeta()
    await waitFor(() => expect(screen.getByTestId('agent-vars')).toBeInTheDocument())
    await userEvent.click(screen.getByRole('tab', { name: 'Beta' }))
  }

  it('says the global variables no longer apply', async () => {
    await inBeta()
    expect(screen.getByTestId('vars-replaced')).toBeInTheDocument()
  })

  it('falls back to the prompt default, not to the global value', async () => {
    await inBeta()
    // `tone` is 'formal' globally, but Beta declares its own vars table, so
    // the runtime hands the agent the prompt's own default instead.
    const notes = screen.getAllByTestId('inherit-note').map((node) => node.textContent)
    expect(notes.some((text) => text?.includes('formal'))).toBe(false)
  })

  it('keeps the global variables for a project that declares none', async () => {
    renderWithBeta()
    await waitFor(() => expect(screen.getByTestId('agent-vars')).toBeInTheDocument())
    await userEvent.click(screen.getByRole('tab', { name: 'Alpha' }))

    const notes = screen.getAllByTestId('inherit-note').map((node) => node.textContent)
    expect(notes.some((text) => text?.includes('formal'))).toBe(true)
    expect(screen.queryByTestId('vars-replaced')).toBeNull()
  })
})

// --- one draft, one meaning ---------------------------------------------

describe('removing every override for one agent in a project', () => {
  it('drops the edits queued inside that override', async () => {
    renderDetail()
    await waitFor(() => expect(screen.getByTestId('agent-settings')).toBeInTheDocument())
    await userEvent.click(screen.getByRole('tab', { name: 'Alpha' }))

    await userEvent.click(screen.getByRole('switch', { name: 'enabled' }))
    await userEvent.click(screen.getByRole('button', { name: 'Remove all overrides' }))

    // The server rejects an overlay holding both a table and a key inside it,
    // so keeping the switch's edit would 400 the preview.
    expect(edits()).toEqual({ 'projects.Alpha.agents.reviewer': null })
  })
})

// --- forking a prompt for a project -------------------------------------
//
// Scope discipline: this action lives on Agent detail only, not on the
// Projects card -- one call site, one dialog, one guard.

/** The body of the (one) POST .../fork request, once it has been sent. */
async function forkRequestBody(): Promise<{ project: string; directory?: string }> {
  await waitFor(() =>
    expect(
      fetchMock.mock.calls.some(
        (call) => (call[1]?.method ?? '') === 'POST' && String(call[0]).includes('/fork'),
      ),
    ).toBe(true),
  )
  const call = fetchMock.mock.calls.find(
    (entry) => (entry[1]?.method ?? '') === 'POST' && String(entry[0]).includes('/fork'),
  )!
  return JSON.parse(String((call[1] as RequestInit).body))
}

describe('forking a prompt for a project', () => {
  const FORK_BUTTON = 'Give this project its own prompt'

  it('does not offer the fork in global scope', async () => {
    await renderAgentDetail({ isAdmin: true, project: null })
    expect(screen.queryByRole('button', { name: FORK_BUTTON })).not.toBeInTheDocument()
  })

  it('does not offer the fork to a non-admin session', async () => {
    await renderAgentDetail({ isAdmin: false, project: 'Car Configurator' })
    expect(screen.queryByRole('button', { name: FORK_BUTTON })).not.toBeInTheDocument()
  })

  it('offers the fork in project scope, to an admin', async () => {
    await renderAgentDetail({ isAdmin: true, project: 'Car Configurator' })
    expect(screen.getByRole('button', { name: FORK_BUTTON })).toBeInTheDocument()
  })

  it('is disabled with a reason while config edits are pending', async () => {
    await renderAgentDetail({ isAdmin: true, project: 'Car Configurator', dirty: true })
    expect(screen.getByRole('button', { name: FORK_BUTTON })).toBeDisabled()
    expect(
      screen.getByText('Apply or discard the pending configuration changes first.'),
    ).toBeInTheDocument()
  })

  it('posts the project and navigates using the SERVER’S own directory name, not a client guess', async () => {
    const { navigate } = await renderAgentDetail({ isAdmin: true, project: 'Car Configurator' })
    await userEvent.click(screen.getByRole('button', { name: FORK_BUTTON }))
    await userEvent.click(screen.getByRole('button', { name: 'Confirm' }))

    await waitFor(() =>
      expect(navigate).toHaveBeenCalledWith('/admin/prompts/de/explainer__car-configurator'),
    )
    // Neither the client-computed agentKey nor a naive project slug: proof
    // the navigation reads the response rather than recomputing the name.
    expect(navigate).not.toHaveBeenCalledWith(expect.stringContaining('reviewer'))
    expect(navigate).not.toHaveBeenCalledWith('/admin/prompts/de/car-configurator')
  })

  it('sends the operator-typed directory override in the fork request', async () => {
    // The whole recovery story for a 400 ("this project name yields no
    // usable directory") is typing one in here, so it has to actually reach
    // the server.
    await renderAgentDetail({ isAdmin: true, project: 'Car Configurator' })
    await userEvent.click(screen.getByRole('button', { name: FORK_BUTTON }))
    await userEvent.type(screen.getByLabelText('Target directory'), 'my-dir')
    await userEvent.click(screen.getByRole('button', { name: 'Confirm' }))

    expect(await forkRequestBody()).toEqual({ project: 'Car Configurator', directory: 'my-dir' })
  })

  it('sends no directory override for a field left whitespace-only', async () => {
    // `.trim() || undefined`: a whitespace-only override is exactly as
    // absent as an empty field, and must not be sent as a literal "   " the
    // server would reject.
    await renderAgentDetail({ isAdmin: true, project: 'Car Configurator' })
    await userEvent.click(screen.getByRole('button', { name: FORK_BUTTON }))
    await userEvent.type(screen.getByLabelText('Target directory'), '   ')
    await userEvent.click(screen.getByRole('button', { name: 'Confirm' }))

    expect(await forkRequestBody()).toEqual({ project: 'Car Configurator' })
  })

  it('surfaces the server’s error text in the dialog instead of swallowing it', async () => {
    forkError = 'The project name has no usable directory name; supply one.'
    await renderAgentDetail({ isAdmin: true, project: 'Car Configurator' })
    await userEvent.click(screen.getByRole('button', { name: FORK_BUTTON }))
    await userEvent.click(screen.getByRole('button', { name: 'Confirm' }))

    await waitFor(() =>
      expect(
        screen.getByText('The project name has no usable directory name; supply one.'),
      ).toBeInTheDocument(),
    )
  })
})
