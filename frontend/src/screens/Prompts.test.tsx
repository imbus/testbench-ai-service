/**
 * The prompt tree screen (design §5.6): one row per agent, one column per
 * language, each cell linking to that language's editor.
 */
import { render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { PromptTreeResponse } from '../api/types'
import { Prompts } from './Prompts'

const TREE: PromptTreeResponse = {
  languages: [
    {
      lang: 'de',
      prompts: [
        {
          agent: 'reviewer',
          file: 'reviewer/prompt.yaml',
          name: 'Reviewer',
          variants: ['Thorough'],
          ok: true,
          error: null,
          used_by: [],
        },
        {
          agent: 'explainer',
          file: 'explainer/prompt.yaml',
          name: null,
          variants: [],
          ok: false,
          error: 'Invalid YAML at line 4',
          used_by: [],
        },
      ],
    },
    {
      lang: 'en',
      prompts: [
        {
          agent: 'reviewer',
          file: 'reviewer/prompt.yaml',
          name: 'Reviewer',
          variants: ['Thorough'],
          ok: true,
          error: null,
          used_by: [],
        },
      ],
    },
  ],
}

let fetchMock: ReturnType<typeof vi.fn>
// `unknown`, not `PromptTreeResponse | null`: one test below sends a 200 body
// that is missing the `languages` field entirely, which is not a value the
// real type can express but is exactly the payload shape the guard exists for.
let treeBody: unknown

beforeEach(() => {
  treeBody = TREE
  fetchMock = vi.fn(async (url: string) => {
    if (url.startsWith('/admin/api/prompts')) {
      if (treeBody === null) {
        return { ok: false, status: 500, json: async () => ({ detail: 'boom' }) } as Response
      }
      return ok(treeBody)
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

function renderPrompts() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <Prompts lang="en" />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

/** No `lang` prop -- exercises the console's actual German default. */
function renderPromptsDefault() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <Prompts />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('Prompts', () => {
  it('lists each agent once, with a column per language', async () => {
    renderPrompts()
    await waitFor(() => expect(screen.getByTestId('prompt-lang-de')).toBeInTheDocument())
    expect(screen.getByTestId('prompt-lang-en')).toBeInTheDocument()
    expect(screen.getAllByTestId('prompt-row-reviewer')).toHaveLength(1)
    const row = screen.getByTestId('prompt-row-reviewer')
    expect(row.textContent).toMatch(/Reviewer/)
    expect(within(row).getAllByRole('link')).toHaveLength(2)
  })

  it('shows the variants of each language file as tags', async () => {
    renderPrompts()
    await waitFor(() => expect(screen.getByTestId('prompt-agent-en-reviewer')).toBeInTheDocument())
    expect(within(screen.getByTestId('prompt-agent-en-reviewer')).getByText('Thorough')).toBeInTheDocument()
  })

  it('marks a language that has no file for the agent', async () => {
    renderPrompts()
    await waitFor(() => expect(screen.getByTestId('prompt-row-explainer')).toBeInTheDocument())
    expect(screen.queryByTestId('prompt-agent-en-explainer')).not.toBeInTheDocument()
    expect(screen.getByTestId('prompt-row-explainer').textContent).toMatch(/no file/)
  })

  it('lists who uses the file, and says so when nobody does', async () => {
    const tree = structuredClone(TREE)
    tree.languages[0].prompts[0].used_by = [
      { agent: 'reviewer', project: null },
      { agent: 'reviewer', project: 'ALPHA' },
    ]
    tree.languages[1].prompts[0].used_by = [{ agent: 'reviewer', project: null }]
    treeBody = tree
    renderPrompts()
    await waitFor(() => expect(screen.getByTestId('prompt-row-reviewer')).toBeInTheDocument())
    const row = screen.getByTestId('prompt-row-reviewer')
    // Deduplicated across languages: one global tag, not one per file.
    expect(within(row).getAllByText('Global')).toHaveLength(1)
    expect(within(row).getByText('ALPHA')).toBeInTheDocument()
    expect(screen.getByTestId('prompt-row-explainer').textContent).toMatch(/unused/)
  })

  it('links each agent to its editor', async () => {
    renderPrompts()
    await waitFor(() => expect(screen.getByTestId('prompt-agent-de-reviewer')).toBeInTheDocument())
    const link = within(screen.getByTestId('prompt-agent-de-reviewer')).getByRole('link')
    expect(link).toHaveAttribute('href', '/admin/prompts/de/reviewer')
  })

  it('shows a badge with the error for a broken prompt, and still links to it', async () => {
    renderPrompts()
    await waitFor(() =>
      expect(screen.getByTestId('prompt-agent-de-explainer')).toBeInTheDocument(),
    )
    const row = screen.getByTestId('prompt-agent-de-explainer')
    expect(row.textContent).toMatch(/Invalid YAML at line 4/)
    const link = within(row).getByRole('link')
    expect(link).toHaveAttribute('href', '/admin/prompts/de/explainer')
  })

  it('shows an empty state for an empty tree', async () => {
    treeBody = { languages: [] }
    renderPrompts()
    await waitFor(() => expect(screen.getByText(/no prompts/i)).toBeInTheDocument())
  })

  // A 200 response is not the same guarantee as a 200 response shaped the way
  // the type says: a payload missing `languages` entirely must still render
  // the empty state, not throw reading `.length`/`.map` off `undefined`.
  it('renders the empty state rather than crashing on a payload missing `languages`', async () => {
    treeBody = {}
    renderPrompts()
    await waitFor(() => expect(screen.getByText(/no prompts/i)).toBeInTheDocument())
  })

  it('shows an error rather than a blank screen on a load failure', async () => {
    treeBody = null
    renderPrompts()
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
  })

  // The screen defaults to German (matching every other screen's own
  // `lang = 'de'` default) -- every test above pins lang="en" to keep its
  // English-text assertions meaningful. This is the one that actually
  // exercises the German dictionary for a key THIS screen reads.
  it('renders the German empty state by default', async () => {
    treeBody = { languages: [] }
    renderPromptsDefault()
    await waitFor(() => expect(screen.getByText('Keine Prompts gefunden.')).toBeInTheDocument())
  })
})
