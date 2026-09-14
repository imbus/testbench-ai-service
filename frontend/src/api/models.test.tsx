import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, expect, test, vi } from 'vitest'
import { useTestPrompt } from './mutations'
import { useModels } from './queries'

afterEach(() => vi.unstubAllGlobals())

const CATALOGUE = {
  providers: [
    {
      provider: 'openai',
      key_present: true,
      models: [{ id: 'gpt-4o', routing: 'chat', source: 'builtin' }],
    },
  ],
}

function stubFetch(body: unknown) {
  const spy = vi.fn().mockResolvedValue(
    new Response(JSON.stringify(body), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
  vi.stubGlobal('fetch', spy)
  return spy
}

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

test('useModels fetches the catalogue', async () => {
  stubFetch(CATALOGUE)
  const { result } = renderHook(() => useModels(), { wrapper })
  await waitFor(() => expect(result.current.isSuccess).toBe(true))
  expect(result.current.data?.providers[0].models[0].id).toBe('gpt-4o')
})

test('useModels passes the project through as a query parameter', async () => {
  const spy = stubFetch(CATALOGUE)
  const { result } = renderHook(() => useModels('Car Configurator'), { wrapper })
  await waitFor(() => expect(result.current.isSuccess).toBe(true))
  expect(String(spy.mock.calls[0][0])).toContain('project=Car%20Configurator')
})

test('useModels omits the query parameter when no project is given', async () => {
  const spy = stubFetch(CATALOGUE)
  const { result } = renderHook(() => useModels(), { wrapper })
  await waitFor(() => expect(result.current.isSuccess).toBe(true))
  expect(String(spy.mock.calls[0][0])).not.toContain('project=')
})

test('useTestPrompt posts the body as JSON', async () => {
  const spy = stubFetch({
    text: 'ok',
    latency_ms: 12,
    resolved: { provider: 'anthropic', model: 'claude-opus-5', credential_scope: 'global' },
  })
  const { result } = renderHook(() => useTestPrompt(), { wrapper })

  result.current.mutate({
    messages: [],
    vars: {},
    agent_context: {},
    model: 'claude-opus-5',
    project: null,
  })

  await waitFor(() => expect(result.current.isSuccess).toBe(true))
  const init = spy.mock.calls[0][1] as RequestInit
  expect(init.method).toBe('POST')
  expect(JSON.parse(init.body as string).model).toBe('claude-opus-5')
  expect(result.current.data?.resolved.credential_scope).toBe('global')
})
