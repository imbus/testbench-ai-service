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
import type { ConfigResponse, ProjectsResponse, PromptMeta } from '../api/types'
import { AgentDetail } from './AgentDetail'

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
  ],
  fetched_at: '2026-09-10T08:00:00Z',
  source: 'testbench',
  error: null,
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

beforeEach(() => {
  window.localStorage.clear()
  metaBody = META
  fetchMock = vi.fn(async (url: string) => {
    if (url.startsWith('/admin/api/config')) return ok(CONFIG)
    if (url.startsWith('/admin/api/projects')) return ok(PROJECTS)
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
