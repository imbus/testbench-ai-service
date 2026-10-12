/**
 * `useProjects`, `useRefreshProjects` and `usePromptMeta` against the step-3
 * routes.
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ReactNode } from 'react'
import { usePromptMeta, useProjects } from './queries'
import { useRefreshProjects } from './mutations'
import type { ProjectsResponse, PromptMeta } from './types'

const PROJECTS: ProjectsResponse = {
  projects: [
    { name: 'Alpha', key: '11' },
    { name: 'Release 2.0', key: '12' },
  ],
  fetched_at: '2026-09-10T08:00:00Z',
  source: 'testbench',
  error: null,
}

const META: PromptMeta = {
  name: 'Reviewer',
  summary: null,
  description: null,
  default_model: 'gpt-5.5',
  default_variant: 'Thorough',
  variants: [
    { name: 'Thorough', description: null, model: 'gpt-5.5', vars: {} },
    { name: 'Quick', description: null, model: null, vars: {} },
  ],
}

let fetchMock: ReturnType<typeof vi.fn>

beforeEach(() => {
  fetchMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

function ok(body: unknown) {
  return {
    ok: true,
    status: 200,
    json: async () => body,
  } as Response
}

function failure(status: number, detail: string) {
  return {
    ok: false,
    status,
    json: async () => ({ detail }),
  } as Response
}

function Wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

// --- useProjects --------------------------------------------------------

describe('useProjects', () => {
  function Probe() {
    const { data } = useProjects()
    if (!data) return <span>…</span>
    return (
      <span data-testid="out">
        {data.source}:{data.projects.map((p) => p.name).join('|')}
      </span>
    )
  }

  it('reads the cached list from GET /projects', async () => {
    fetchMock.mockResolvedValue(ok(PROJECTS))
    render(
      <Wrapper>
        <Probe />
      </Wrapper>,
    )
    await waitFor(() =>
      expect(screen.getByTestId('out')).toHaveTextContent('testbench:Alpha|Release 2.0'),
    )
    expect(fetchMock.mock.calls[0][0]).toBe('/admin/api/projects')
  })

  it('does not poll — the cache only changes on an explicit refresh', () => {
    // A refetchInterval here would spend a request every few seconds on a list
    // the server only re-reads when asked, which is the whole point of D3.
    expect(useProjects.toString()).not.toContain('refetchInterval')
  })
})

// --- useRefreshProjects -------------------------------------------------

describe('useRefreshProjects', () => {
  function Probe() {
    const refresh = useRefreshProjects()
    return (
      <button type="button" onClick={() => refresh.mutate()}>
        refresh
      </button>
    )
  }

  it('posts to /projects/refresh', async () => {
    fetchMock.mockResolvedValue(ok(PROJECTS))
    render(
      <Wrapper>
        <Probe />
      </Wrapper>,
    )
    await userEvent.click(screen.getByRole('button'))
    await waitFor(() => expect(fetchMock).toHaveBeenCalled())
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/admin/api/projects/refresh')
    expect(init.method).toBe('POST')
  })

  it('replaces the cached query data so the screen re-renders', async () => {
    function Both() {
      const { data } = useProjects()
      const refresh = useRefreshProjects()
      return (
        <>
          <span data-testid="out">{(data?.projects ?? []).map((p) => p.name).join('|')}</span>
          <button type="button" onClick={() => refresh.mutate()}>
            refresh
          </button>
        </>
      )
    }

    fetchMock.mockResolvedValueOnce(ok(PROJECTS))
    render(
      <Wrapper>
        <Both />
      </Wrapper>,
    )
    await waitFor(() => expect(screen.getByTestId('out')).toHaveTextContent('Alpha'))

    fetchMock.mockResolvedValue(
      ok({ ...PROJECTS, projects: [{ name: 'Gamma', key: '13' }] }),
    )
    await userEvent.click(screen.getByRole('button'))
    await waitFor(() => expect(screen.getByTestId('out')).toHaveTextContent('Gamma'))
  })
})

// --- usePromptMeta ------------------------------------------------------

describe('usePromptMeta', () => {
  function Probe({
    lang,
    agent,
    file,
    enabled = true,
  }: {
    lang: string
    agent: string
    file?: string
    enabled?: boolean
  }) {
    const { data, isError } = usePromptMeta(lang, agent, file, { enabled })
    if (isError) return <span data-testid="out">error</span>
    if (!data) return <span>…</span>
    return <span data-testid="out">{data.variants.map((v) => v.name).join('|')}</span>
  }

  it('requests the metadata for one agent in one language', async () => {
    fetchMock.mockResolvedValue(ok(META))
    render(
      <Wrapper>
        <Probe lang="de" agent="test_case_set_reviewer" />
      </Wrapper>,
    )
    await waitFor(() => expect(screen.getByTestId('out')).toHaveTextContent('Thorough|Quick'))
    expect(fetchMock.mock.calls[0][0]).toBe(
      '/admin/api/prompts/de/test_case_set_reviewer/meta',
    )
  })

  it('passes the draft prompt file as ?file=', async () => {
    fetchMock.mockResolvedValue(ok(META))
    render(
      <Wrapper>
        <Probe lang="de" agent="x" file="other/prompt.yaml" />
      </Wrapper>,
    )
    await waitFor(() => expect(fetchMock).toHaveBeenCalled())
    expect(fetchMock.mock.calls[0][0]).toBe(
      '/admin/api/prompts/de/x/meta?file=other%2Fprompt.yaml',
    )
  })

  it('percent-encodes an agent key and a language that need it', async () => {
    // The segments come from config keys, which are operator-controlled. An
    // unencoded '/' or '#' would silently address a different route.
    fetchMock.mockResolvedValue(ok(META))
    render(
      <Wrapper>
        <Probe lang="de" agent="a/b#c" />
      </Wrapper>,
    )
    await waitFor(() => expect(fetchMock).toHaveBeenCalled())
    expect(fetchMock.mock.calls[0][0]).toBe('/admin/api/prompts/de/a%2Fb%23c/meta')
  })

  it('does not fire while disabled', () => {
    render(
      <Wrapper>
        <Probe lang="de" agent="x" enabled={false} />
      </Wrapper>,
    )
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('does not fire without an agent key', () => {
    // Agent detail renders before a scope is chosen, and a request for the
    // empty agent key would be a guaranteed 404 on every such render.
    render(
      <Wrapper>
        <Probe lang="de" agent="" />
      </Wrapper>,
    )
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('surfaces a 404 as an error rather than retrying', async () => {
    // A missing prompt file is a real answer the form has to render around
    // (free-text variant instead of a select), not a transient failure.
    fetchMock.mockResolvedValue(failure(404, 'No prompt file'))
    render(
      <Wrapper>
        <Probe lang="de" agent="x" />
      </Wrapper>,
    )
    await waitFor(() => expect(screen.getByTestId('out')).toHaveTextContent('error'))
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('caches per language, agent and file', async () => {
    function Two() {
      usePromptMeta('de', 'x')
      usePromptMeta('en', 'x')
      usePromptMeta('de', 'x', 'other.yaml')
      usePromptMeta('de', 'x')
      return <span>ok</span>
    }
    fetchMock.mockResolvedValue(ok(META))
    render(
      <Wrapper>
        <Two />
      </Wrapper>,
    )
    // Three distinct keys, and the repeat of the first shares its cache entry.
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3))
  })
})
