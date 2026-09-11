/**
 * The prompt tree screen (design §5.6): one section per language, one link
 * per agent, pointed at its editor.
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
        },
        {
          agent: 'explainer',
          file: 'explainer/prompt.yaml',
          name: null,
          variants: [],
          ok: false,
          error: 'Invalid YAML at line 4',
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
        },
      ],
    },
  ],
}

let fetchMock: ReturnType<typeof vi.fn>
let treeBody: PromptTreeResponse | null

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

describe('Prompts', () => {
  it('lists each language and its agents', async () => {
    renderPrompts()
    await waitFor(() => expect(screen.getByTestId('prompt-lang-de')).toBeInTheDocument())
    expect(screen.getByTestId('prompt-lang-en')).toBeInTheDocument()
    expect(
      within(screen.getByTestId('prompt-lang-de')).getByRole('link', { name: 'Reviewer' }),
    ).toBeInTheDocument()
  })

  it('links each agent to its editor', async () => {
    renderPrompts()
    await waitFor(() => expect(screen.getByTestId('prompt-agent-de-reviewer')).toBeInTheDocument())
    const link = within(screen.getByTestId('prompt-agent-de-reviewer')).getByRole('link')
    expect(link).toHaveAttribute('href', '/prompts/de/reviewer')
  })

  it('shows a badge with the error for a broken prompt, and still links to it', async () => {
    renderPrompts()
    await waitFor(() =>
      expect(screen.getByTestId('prompt-agent-de-explainer')).toBeInTheDocument(),
    )
    const row = screen.getByTestId('prompt-agent-de-explainer')
    expect(row.textContent).toMatch(/Invalid YAML at line 4/)
    const link = within(row).getByRole('link')
    expect(link).toHaveAttribute('href', '/prompts/de/explainer')
  })

  it('shows an empty state for an empty tree', async () => {
    treeBody = { languages: [] }
    renderPrompts()
    await waitFor(() => expect(screen.getByText(/no prompts/i)).toBeInTheDocument())
  })

  it('shows an error rather than a blank screen on a load failure', async () => {
    treeBody = null
    renderPrompts()
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
  })
})
