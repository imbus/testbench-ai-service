/**
 * The Projects screen (design §5.4): one card per project over the union of
 * the cached TestBench list and the projects `config.toml` declares.
 */
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { DraftProvider, useDraft } from '../state/draft'
import type { ConfigResponse, ProjectsResponse } from '../api/types'
import { Projects } from './Projects'
import { i18n } from '../i18n'

// The assertions match the English copy.
beforeEach(() => i18n.changeLanguage('en'))

const DISK = {
  language: 'de',
  agents: {
    reviewer: { enabled: true, endpoint_path: '/r', class_path: 'a.R', prompt: { file: 'r.yaml' } },
    explainer: {
      enabled: false,
      endpoint_path: '/e',
      class_path: 'a.E',
      prompt: { file: 'e.yaml' },
    },
  },
  projects: {
    Alpha: { language: 'en', agents: { reviewer: { enabled: false } } },
    Legacy: { agents: { explainer: { enabled: true } } },
    Modelled: { llm_config: { provider: 'anthropic', model: 'claude-x' } },
  },
}

const CONFIG: ConfigResponse = { running: DISK, disk: DISK, config_path: 'C:/svc/config.toml' }

const AVAILABLE: ProjectsResponse = {
  projects: [
    { name: 'Alpha', key: '11' },
    { name: 'Modelled', key: '12' },
    { name: 'Fresh', key: '13' },
  ],
  fetched_at: '2026-09-10T08:00:00Z',
  source: 'testbench',
  error: null,
}

const UNAVAILABLE: ProjectsResponse = {
  projects: [],
  fetched_at: '2026-09-10T08:00:00Z',
  source: 'unavailable',
  error: 'TestBench did not respond in time',
}

let fetchMock: ReturnType<typeof vi.fn>
let projectsBody: ProjectsResponse

beforeEach(() => {
  window.localStorage.clear()
  projectsBody = AVAILABLE
  fetchMock = vi.fn(async (url: string) => {
    if (url.startsWith('/admin/api/config')) return ok(CONFIG)
    if (url === '/admin/api/projects/refresh') return ok(AVAILABLE)
    if (url.startsWith('/admin/api/projects')) return ok(projectsBody)
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

function renderProjects({ isAdmin = true }: { isAdmin?: boolean } = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <DraftProvider saved={DISK}>
          <Projects isAdmin={isAdmin} issues={[]} />
          <Edits />
        </DraftProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

async function ready() {
  await waitFor(() => expect(screen.getByTestId('project-Alpha')).toBeInTheDocument())
}

// --- the union ----------------------------------------------------------

describe('which projects get a card', () => {
  it('shows a project that exists in both TestBench and the config', async () => {
    await renderProjects()
    await ready()
    expect(screen.getByTestId('project-Alpha')).toBeInTheDocument()
  })

  it('shows a TestBench project with no config block yet', async () => {
    renderProjects()
    await ready()
    expect(screen.getByTestId('project-Fresh')).toBeInTheDocument()
  })

  it('shows a config-only project, flagged as absent from TestBench', async () => {
    // Dropping it would hide overrides the operator has to be able to find --
    // and a project that has been renamed or deleted in TestBench is exactly
    // the case that needs attention.
    renderProjects()
    await ready()
    const card = screen.getByTestId('project-Legacy')
    expect(card).toHaveAttribute('data-in-testbench', 'false')
    expect(card.textContent).toMatch(/not in TestBench/i)
  })

  it('does not flag a project TestBench knows about', async () => {
    renderProjects()
    await ready()
    expect(screen.getByTestId('project-Alpha')).toHaveAttribute('data-in-testbench', 'true')
  })

  it('lists each project once even when it is in both sources', async () => {
    renderProjects()
    await ready()
    expect(screen.getAllByTestId('project-Alpha')).toHaveLength(1)
  })
})

// --- per-project settings ----------------------------------------------

describe('a project card', () => {
  it('offers the language override as a three-way choice', async () => {
    renderProjects()
    await ready()
    // A SelectButton: a named group of toggle buttons, the pick marked pressed.
    const group = within(screen.getByTestId('project-Alpha')).getByRole('group', {
      name: 'language',
    })

    expect(within(group).getAllByRole('button')).toHaveLength(3)
    expect(within(group).getByRole('button', { name: 'en' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    expect(within(group).getByRole('button', { name: /Inherited/ })).toHaveAttribute(
      'aria-pressed',
      'false',
    )
  })

  it('writes the language override to the project path', async () => {
    renderProjects()
    await ready()
    const card = screen.getByTestId('project-Fresh')

    await userEvent.click(within(card).getByRole('button', { name: 'en' }))

    expect(edits()).toEqual({ 'projects.Fresh.language': 'en' })
  })

  it('takes the override back off again', async () => {
    // The reason this is a segment and not a select: "inherit" is a state the
    // operator picks, not the absence of a pick.
    renderProjects()
    await ready()
    const card = screen.getByTestId('project-Alpha')

    await userEvent.click(within(card).getByRole('button', { name: /Inherited/ }))

    expect(edits()).toEqual({ 'projects.Alpha.language': null })
  })

  it('says a project with no language override inherits the global one', async () => {
    renderProjects()
    await ready()
    const card = screen.getByTestId('project-Legacy')

    const inheriting = within(card).getByRole('button', { name: /Inherited/ })
    expect(inheriting).toHaveAttribute('aria-pressed', 'true')
    expect(inheriting.textContent).toMatch(/de/)
  })

  it('has an on/off switch per agent', async () => {
    renderProjects()
    await ready()
    const card = screen.getByTestId('project-Alpha')
    expect(within(card).getByRole('switch', { name: /reviewer/ })).toHaveAttribute(
      'data-state',
      'off',
    )
    expect(within(card).getByRole('switch', { name: /explainer/ })).toHaveAttribute(
      'data-state',
      'inherit',
    )
    expect(within(card).getByRole('switch', { name: /reviewer/ })).toHaveAttribute(
      'aria-checked',
      'false',
    )
  })

  it('writes an agent toggle to the project override path', async () => {
    renderProjects()
    await ready()
    const card = screen.getByTestId('project-Fresh')
    // explainer is off globally, so switching it here turns it on.
    await userEvent.click(within(card).getByRole('switch', { name: /explainer/ }))
    expect(edits()).toEqual({ 'projects.Fresh.agents.explainer.enabled': true })
  })

  it('removes every override for the project as a single edit', async () => {
    renderProjects()
    await ready()
    const card = screen.getByTestId('project-Alpha')
    await userEvent.click(within(card).getByRole('button', { name: /remove all overrides/i }))
    // One null on the project table: the server reads it as "delete the key",
    // which is exactly "this project has no overrides at all".
    expect(edits()).toEqual({ 'projects.Alpha': null })
  })

  it('offers no removal for a project that has no config block', async () => {
    renderProjects()
    await ready()
    const card = screen.getByTestId('project-Fresh')
    expect(
      within(card).queryByRole('button', { name: /remove all overrides/i }),
    ).not.toBeInTheDocument()
  })
})

// --- llm_config ---------------------------------------------------------

describe('a project that carries an llm_config block', () => {
  it('leaves it to the LLM screen', async () => {
    // The model is picked per agent on the Agents screen and the rest of
    // llm_config on the LLM screen; the card does not repeat either.
    renderProjects()
    await ready()
    const card = screen.getByTestId('project-Modelled')
    expect(within(card).queryByTestId('project-llm-config')).not.toBeInTheDocument()
    expect(card.textContent).not.toContain('claude-x')
  })
})

// --- staleness and refresh ---------------------------------------------

describe('the cached list', () => {
  it('says when it was fetched', async () => {
    // Risk 4: the cache can be up to the session's absolute cap stale, so the
    // operator needs to see its age before trusting a missing project.
    renderProjects()
    await ready()
    expect(screen.getByTestId('projects-fetched-at')).toBeInTheDocument()
  })

  it('can be refreshed', async () => {
    renderProjects()
    await ready()
    await userEvent.click(screen.getByRole('button', { name: /refresh/i }))
    await waitFor(() =>
      expect(fetchMock.mock.calls.some((call) => call[0] === '/admin/api/projects/refresh')).toBe(
        true,
      ),
    )
  })

  it('offers no refresh to a non-admin — it spends the stored credential', async () => {
    renderProjects({ isAdmin: false })
    await ready()
    expect(screen.queryByRole('button', { name: /refresh/i })).not.toBeInTheDocument()
  })
})

// --- the unavailable fallback ------------------------------------------

describe('when TestBench could not be asked', () => {
  beforeEach(() => {
    projectsBody = UNAVAILABLE
  })

  it('says so, with the reason', async () => {
    renderProjects()
    await waitFor(() => expect(screen.getByTestId('projects-unavailable')).toBeInTheDocument())
    expect(screen.getByTestId('projects-unavailable').textContent).toMatch(/did not respond/)
  })

  it('still shows the projects the config declares', async () => {
    renderProjects()
    await waitFor(() => expect(screen.getByTestId('project-Legacy')).toBeInTheDocument())
  })

  it('does not claim a project is missing from TestBench it could not ask', async () => {
    renderProjects()
    await waitFor(() => expect(screen.getByTestId('project-Legacy')).toBeInTheDocument())
    expect(screen.getByTestId('project-Legacy').textContent).not.toMatch(/not in TestBench/i)
  })

  it('offers a free-text project name, warning that it must match exactly', async () => {
    renderProjects()
    await waitFor(() => expect(screen.getByTestId('add-by-name')).toBeInTheDocument())
    expect(screen.getByTestId('add-by-name').textContent).toMatch(/exactly/i)
  })

  it('adds a card for a name typed by hand, without writing anything yet', async () => {
    renderProjects()
    await waitFor(() => expect(screen.getByTestId('add-by-name')).toBeInTheDocument())

    await userEvent.type(screen.getByLabelText('Project name'), 'Release 2.0')
    await userEvent.click(screen.getByRole('button', { name: 'Add' }))

    expect(screen.getByTestId('project-Release 2.0')).toBeInTheDocument()
    expect(edits()).toEqual({})
  })

  it('quotes a hand-typed dotted name when an override is set on it', async () => {
    // The whole reason the tokenizer exists: unquoted, `Release 2.0` splits
    // into two segments and addresses nothing the server recognises.
    renderProjects()
    await waitFor(() => expect(screen.getByTestId('add-by-name')).toBeInTheDocument())

    await userEvent.type(screen.getByLabelText('Project name'), 'Release 2.0')
    await userEvent.click(screen.getByRole('button', { name: 'Add' }))
    const card = screen.getByTestId('project-Release 2.0')
    await userEvent.click(within(card).getByRole('switch', { name: /reviewer/ }))

    expect(edits()).toEqual({ 'projects."Release 2.0".agents.reviewer.enabled': false })
  })

  it('ignores a blank name', async () => {
    renderProjects()
    await waitFor(() => expect(screen.getByTestId('add-by-name')).toBeInTheDocument())
    await userEvent.click(screen.getByRole('button', { name: 'Add' }))
    expect(screen.queryByTestId('project-')).not.toBeInTheDocument()
  })
})

describe('when TestBench answered', () => {
  it('offers no free-text name — the list is authoritative', async () => {
    // Typing a name that must match TestBench exactly is a footgun; it is only
    // worth offering when the console genuinely cannot know the real names.
    renderProjects()
    await ready()
    expect(screen.queryByTestId('add-by-name')).not.toBeInTheDocument()
  })
})

// --- read-only sessions -------------------------------------------------

describe('a non-admin session', () => {
  it('renders the cards without editable controls', async () => {
    renderProjects({ isAdmin: false })
    await ready()
    const card = screen.getByTestId('project-Alpha')
    expect(within(card).getByRole('switch', { name: /reviewer/ })).toBeDisabled()
    expect(
      within(card).queryByRole('button', { name: /remove all overrides/i }),
    ).not.toBeInTheDocument()
  })
})

describe('a config payload with nothing in it', () => {
  it('renders rather than crashing', async () => {
    fetchMock.mockImplementation(async (url: string) => {
      if (url.startsWith('/admin/api/config')) return ok({ config_path: 'x' })
      if (url.startsWith('/admin/api/projects')) return ok(AVAILABLE)
      return { ok: false, status: 404, json: async () => ({ detail: 'no' }) } as Response
    })
    renderProjects()
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'Projects' })).toBeInTheDocument(),
    )
  })
})

// --- one draft, one meaning ---------------------------------------------

describe('removing every override for a project', () => {
  it('drops the edits queued inside that project', async () => {
    renderProjects()
    await ready()
    const alpha = within(screen.getByTestId('project-Alpha'))

    await userEvent.click(alpha.getByRole('switch', { name: /reviewer · Alpha/ }))
    await userEvent.click(alpha.getByRole('button', { name: 'Remove all overrides' }))

    // Not both: the server refuses an overlay carrying a path and a prefix of
    // it, so preview and apply would 400 with no way back but Discard all.
    expect(edits()).toEqual({ 'projects.Alpha': null })
  })
})
