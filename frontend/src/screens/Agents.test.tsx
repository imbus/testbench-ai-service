/**
 * The Agents screen: a list view and an agents × projects matrix (design §5.4).
 */
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { DraftProvider, useDraft } from '../state/draft'
import type { ConfigResponse, ProjectsResponse, PromptMeta } from '../api/types'
import { Agents } from './Agents'

const DISK = {
  agents: {
    reviewer: {
      enabled: true,
      endpoint_path: '/test-case-set-reviews',
      class_path: 'a.b.Reviewer',
      prompt: { file: 'reviewer/prompt.yaml' },
    },
    explainer: {
      enabled: false,
      endpoint_path: '/defect-explanations',
      class_path: 'a.b.Explainer',
      prompt: { file: 'explainer/prompt.yaml' },
    },
  },
  projects: {
    Alpha: { agents: { reviewer: { enabled: false } } },
    'Release 2.0': { agents: { reviewer: { prompt: { variant: 'Quick' } } } },
    Gone: { agents: { explainer: { enabled: true } } },
  },
}

const CONFIG: ConfigResponse = {
  running: DISK,
  disk: DISK,
  config_path: 'C:/svc/config.toml',
}

const PROJECTS: ProjectsResponse = {
  projects: [
    { name: 'Alpha', key: '11' },
    { name: 'Release 2.0', key: '12' },
  ],
  fetched_at: '2026-09-10T08:00:00Z',
  source: 'testbench',
  error: null,
}

function meta(name: string): PromptMeta {
  return {
    name,
    summary: null,
    description: null,
    default_model: 'gpt-5.5',
    default_variant: 'Thorough',
    variants: [{ name: 'Thorough', description: null, model: null, vars: {} }],
  }
}

let fetchMock: ReturnType<typeof vi.fn>
let projectsBody: ProjectsResponse

beforeEach(() => {
  window.localStorage.clear()
  projectsBody = PROJECTS
  fetchMock = vi.fn(async (url: string) => {
    if (url.startsWith('/admin/api/config')) return ok(CONFIG)
    if (url.startsWith('/admin/api/projects')) return ok(projectsBody)
    if (url.includes('/prompts/de/reviewer/')) return ok(meta('Test Case Set Reviewer'))
    if (url.includes('/prompts/de/explainer/')) return ok(meta('Defect Explainer'))
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

function renderAgents({ isAdmin = true }: { isAdmin?: boolean } = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <DraftProvider saved={DISK}>
          <Agents lang="en" isAdmin={isAdmin} />
          <Edits />
        </DraftProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

// --- the list view ------------------------------------------------------

describe('list view', () => {
  it('lists every agent the config declares', async () => {
    renderAgents()
    await waitFor(() => expect(screen.getByText('reviewer')).toBeInTheDocument())
    expect(screen.getByText('explainer')).toBeInTheDocument()
  })

  it('shows each agent’s endpoint path', async () => {
    renderAgents()
    await waitFor(() =>
      expect(screen.getByText('/test-case-set-reviews')).toBeInTheDocument(),
    )
  })

  it('names each agent from its prompt metadata', async () => {
    // The agent key is a config identifier; the prompt's `name` is what a
    // human called it, and it is the only human-readable name that exists.
    renderAgents()
    await waitFor(() =>
      expect(screen.getByText('Test Case Set Reviewer')).toBeInTheDocument(),
    )
  })

  it('still lists an agent whose prompt metadata cannot be read', async () => {
    fetchMock.mockImplementation(async (url: string) => {
      if (url.startsWith('/admin/api/config')) return ok(CONFIG)
      if (url.startsWith('/admin/api/projects')) return ok(PROJECTS)
      return { ok: false, status: 404, json: async () => ({ detail: 'gone' }) } as Response
    })
    renderAgents()
    // The row is the operator's way to fix the broken prompt path, so losing
    // it because the path is broken would be self-defeating.
    await waitFor(() => expect(screen.getByText('reviewer')).toBeInTheDocument())
  })

  it('links each agent to its detail screen', async () => {
    renderAgents()
    await waitFor(() => expect(screen.getByText('reviewer')).toBeInTheDocument())
    expect(screen.getByRole('link', { name: /reviewer/ })).toHaveAttribute(
      'href',
      '/admin/agents/reviewer',
    )
  })

  it('toggles an agent on and off in place', async () => {
    renderAgents()
    await waitFor(() => expect(screen.getByText('reviewer')).toBeInTheDocument())

    await userEvent.click(screen.getByRole('switch', { name: /reviewer/ }))

    expect(edits()).toEqual({ 'agents.reviewer.enabled': false })
  })

  it('counts the projects that override each agent', async () => {
    renderAgents()
    await waitFor(() => expect(screen.getByText('reviewer')).toBeInTheDocument())
    const row = screen.getByTestId('agent-row-reviewer')
    // Alpha and Release 2.0 override reviewer; Gone overrides explainer only.
    expect(within(row).getByTestId('override-count')).toHaveTextContent('2')
  })

  it('names the overriding projects when the row is expanded', async () => {
    renderAgents()
    await waitFor(() => expect(screen.getByText('reviewer')).toBeInTheDocument())

    await userEvent.click(
      within(screen.getByTestId('agent-row-reviewer')).getByRole('button', {
        name: /overrides/i,
      }),
    )

    const detail = screen.getByTestId('agent-overrides-reviewer')
    expect(within(detail).getByText('Alpha')).toBeInTheDocument()
    expect(within(detail).getByText('Release 2.0')).toBeInTheDocument()
  })

  it('counts the projects that override an agent', async () => {
    renderAgents()
    await waitFor(() => expect(screen.getByText('explainer')).toBeInTheDocument())
    const row = screen.getByTestId('agent-row-explainer')
    // `Gone` is the only project with an explainer block.
    expect(within(row).getByTestId('override-count')).toHaveTextContent('1')
  })

  it('offers no expander for an agent no project overrides', async () => {
    fetchMock.mockImplementation(async (url: string) => {
      if (url.startsWith('/admin/api/config'))
        return ok({
          running: { agents: DISK.agents },
          disk: { agents: DISK.agents },
          config_path: 'C:/svc/config.toml',
        })
      if (url.startsWith('/admin/api/projects')) return ok(PROJECTS)
      if (url.includes('/prompts/')) return ok(meta('Reviewer'))
      return { ok: false, status: 404, json: async () => ({ detail: 'no' }) } as Response
    })
    renderAgents()
    await waitFor(() => expect(screen.getByText('explainer')).toBeInTheDocument())
    const row = screen.getByTestId('agent-row-explainer')

    expect(within(row).getByTestId('override-count')).toHaveTextContent('0')
    expect(within(row).queryByRole('button', { name: /overrid/i })).toBeNull()
  })

  it('renders read-only for a non-admin session', async () => {
    renderAgents({ isAdmin: false })
    await waitFor(() => expect(screen.getByText('reviewer')).toBeInTheDocument())
    expect(screen.getByRole('switch', { name: /reviewer/ })).toBeDisabled()
  })
})

// --- the matrix view ----------------------------------------------------

describe('matrix view', () => {
  async function showMatrix() {
    renderAgents()
    await waitFor(() => expect(screen.getByText('reviewer')).toBeInTheDocument())
    await userEvent.click(screen.getByRole('tab', { name: /matrix/i }))
  }

  it('has a column per project from the cached list', async () => {
    await showMatrix()
    expect(screen.getByRole('columnheader', { name: /Alpha/ })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: /Release 2\.0/ })).toBeInTheDocument()
  })

  it('has a row per agent', async () => {
    await showMatrix()
    expect(screen.getByRole('rowheader', { name: /reviewer/ })).toBeInTheDocument()
    expect(screen.getByRole('rowheader', { name: /explainer/ })).toBeInTheDocument()
  })

  it('gives a column to a project that has overrides but is not in TestBench', async () => {
    // Losing the column would hide an override the operator has to be able to
    // find and remove -- and it is exactly the case that needs attention.
    await showMatrix()
    expect(screen.getByRole('columnheader', { name: /Gone/ })).toBeInTheDocument()
  })

  it('flags a config-only project column', async () => {
    await showMatrix()
    expect(screen.getByTestId('column-Gone')).toHaveAttribute('data-in-testbench', 'false')
    expect(screen.getByTestId('column-Alpha')).toHaveAttribute('data-in-testbench', 'true')
  })

  it('shows the overriding cell as off and the inheriting ones as inherit', async () => {
    await showMatrix()
    expect(screen.getByLabelText(/reviewer.*Alpha/)).toHaveAttribute('data-state', 'off')
    expect(screen.getByLabelText(/explainer.*Alpha/)).toHaveAttribute('data-state', 'inherit')
  })

  it('writes a tri-state cycle to the project override path', async () => {
    await showMatrix()

    await userEvent.click(screen.getByLabelText(/explainer.*Release 2\.0/))

    expect(edits()).toEqual({ 'projects."Release 2.0".agents.explainer.enabled': false })
  })

  it('says so instead of drawing an empty grid when there are no projects', async () => {
    projectsBody = { projects: [], fetched_at: null, source: 'unavailable', error: 'down' }
    renderAgents()
    await waitFor(() => expect(screen.getByText('reviewer')).toBeInTheDocument())
    await userEvent.click(screen.getByRole('tab', { name: /matrix/i }))
    // `Gone` is config-only, so it is still a column; the point is the
    // unavailable notice appears rather than the list silently looking short.
    expect(screen.getByTestId('projects-unavailable')).toBeInTheDocument()
  })
})

describe('the matrix against an unapplied draft', () => {
  it('resolves an inheriting cell through the pending global switch', async () => {
    // The cell's accessible label states the value that actually applies --
    // that is the whole reason it exists, since colour alone cannot say it.
    // Reading only the saved config would make it state the opposite of what
    // this draft applies.
    renderAgents()
    await waitFor(() => expect(screen.getByText('reviewer')).toBeInTheDocument())

    await userEvent.click(screen.getByRole('switch', { name: /reviewer/ }))
    await userEvent.click(screen.getByRole('tab', { name: /matrix/i }))

    const cell = screen.getByLabelText(/reviewer.*Release 2\.0/)
    expect(cell).toHaveAttribute('data-state', 'inherit')
    expect(cell.getAttribute('aria-label')).toMatch(/off/i)
  })
})

describe('a config payload with nothing in it', () => {
  it('renders rather than crashing', async () => {
    // `running`/`disk` are whatever the server sent. A response without them
    // must show an empty screen, not take the console down -- an operator who
    // cannot load the console cannot fix the config either.
    fetchMock.mockImplementation(async (url: string) => {
      if (url.startsWith('/admin/api/config')) return ok({ config_path: 'x' })
      if (url.startsWith('/admin/api/projects')) return ok(PROJECTS)
      return { ok: false, status: 404, json: async () => ({ detail: 'no' }) } as Response
    })
    renderAgents()
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'Agents' })).toBeInTheDocument(),
    )
  })
})
