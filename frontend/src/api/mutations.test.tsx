import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from './client'
import { useApply, usePreview } from './mutations'

const fetchMock = vi.fn()

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response
}

beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock)
  document.cookie = 'tbai_admin_csrf=token-123'
  fetchMock.mockReset()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('usePreview', () => {
  it('posts the edits to the preview route', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        valid: true,
        issues: [],
        diffs: [],
        restart_required: [],
        in_flight_tasks: 0,
        toml: '',
      }),
    )
    const { result } = renderHook(() => usePreview(), { wrapper })

    result.current.mutate({ port: 9999 })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/admin/api/config/preview')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body)).toEqual({ edits: { port: 9999 } })
  })

  it('sends the CSRF header', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        valid: true,
        issues: [],
        diffs: [],
        restart_required: [],
        in_flight_tasks: 0,
        toml: '',
      }),
    )
    const { result } = renderHook(() => usePreview(), { wrapper })

    result.current.mutate({})
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    const [, init] = fetchMock.mock.calls[0]
    expect(new Headers(init.headers).get('X-CSRF-Token')).toBe('token-123')
  })

  it('surfaces a validation response as data, not an error', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        valid: false,
        issues: [{ path: 'port', message: 'not an integer', toml_section: '[x]' }],
        diffs: [],
        restart_required: [],
        in_flight_tasks: 0,
        toml: '',
      }),
    )
    const { result } = renderHook(() => usePreview(), { wrapper })

    result.current.mutate({ port: 'nope' })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data?.valid).toBe(false)
    expect(result.current.data?.issues[0].path).toBe('port')
  })
})

describe('useApply', () => {
  it('posts the edits to the apply route', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        written: ['/tmp/config.toml'],
        backup: '/tmp/config.toml.bak',
        restart_required: [],
        reloaded: true,
        in_flight_tasks: 0,
        reload_detail: null,
      }),
    )
    const { result } = renderHook(() => useApply(), { wrapper })

    result.current.mutate({ language: 'en' })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/admin/api/config/apply')
    expect(JSON.parse(init.body)).toEqual({ edits: { language: 'en' } })
  })

  it('reports a 422 as an error carrying the server detail', async () => {
    const detailObj = { message: 'not valid', issues: [{ path: 'port', message: 'invalid' }] }
    fetchMock.mockResolvedValue(
      jsonResponse({ detail: detailObj }, 422),
    )
    const { result } = renderHook(() => useApply(), { wrapper })

    result.current.mutate({ port: 'nope' })
    await waitFor(() => expect(result.current.isError).toBe(true))

    const error = result.current.error as ApiError
    expect(error.detail).toEqual(detailObj)
    const detail = error.detail as Record<string, unknown>
    expect((detail.issues as Array<Record<string, unknown>>)[0].path).toBe('port')
  })
})
