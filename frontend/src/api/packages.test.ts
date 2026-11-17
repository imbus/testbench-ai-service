import { createElement, type ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, apiFetch } from './client'
import {
  conflictsOf,
  packageErrorKey,
  useNotedRestart,
  useActivateVersion,
  useDeleteVersion,
  useRegisterAgents,
  useRemovePackage,
  useUploadPackage,
} from './packages'

const fetchMock = vi.fn()
let client: QueryClient

function wrapper({ children }: { children: ReactNode }) {
  return createElement(QueryClientProvider, { client }, children)
}

function jsonResponse(body: unknown, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as Response
}

const RESULT = { written: ['config.toml'], backup: null, restart_required: ['agent_packages'] }

beforeEach(() => {
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  vi.stubGlobal('fetch', fetchMock)
  document.cookie = 'tbai_admin_csrf=token-123'
  fetchMock.mockReset()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('apiFetch with a form body', () => {
  it('leaves the content type to the browser', async () => {
    fetchMock.mockResolvedValue(jsonResponse({}))
    const body = new FormData()
    body.append('file', new Blob(['x']), 'a.whl')

    await apiFetch('/agent-packages', { method: 'POST', body })

    const headers = new Headers(fetchMock.mock.calls[0][1].headers)
    expect(headers.get('Content-Type')).toBeNull()
    expect(headers.get('X-CSRF-Token')).toBe('token-123')
  })
})

describe('useUploadPackage', () => {
  it('posts the wheel as multipart field "file"', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ name: 'acme', version: '1.0' }))
    const { result } = renderHook(() => useUploadPackage(), { wrapper })
    const file = new File(['wheel'], 'acme-1.0-py3-none-any.whl')

    result.current.mutate(file)
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/admin/api/agent-packages')
    expect(init.method).toBe('POST')
    expect((init.body as FormData).get('file')).toBe(file)
  })
})

describe('useRegisterAgents', () => {
  it('posts the agents and the files to overwrite, and invalidates the screens', async () => {
    fetchMock.mockResolvedValue(jsonResponse(RESULT))
    const invalidate = vi.spyOn(client, 'invalidateQueries')
    const { result } = renderHook(() => useRegisterAgents(), { wrapper })
    const agents = [
      { entry_point: 'risk', agent_key: 'risk', endpoint_path: '/risk', enabled: true },
    ]

    result.current.mutate({
      name: 'acme',
      version: '1.0',
      agents,
      overwrite: ['prompts/x'],
      keep: ['prompts/y'],
    })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/admin/api/agent-packages/acme/1.0/register')
    expect(JSON.parse(init.body)).toEqual({ agents, overwrite: ['prompts/x'], keep: ['prompts/y'] })
    const keys = invalidate.mock.calls.map(([filters]) => filters?.queryKey)
    expect(keys).toEqual(expect.arrayContaining([['packages'], ['config'], ['status']]))
  })

  it('remembers the restart the result asks for', async () => {
    fetchMock.mockResolvedValue(jsonResponse(RESULT))
    const { result } = renderHook(
      () => ({ register: useRegisterAgents(), noted: useNotedRestart(undefined) }),
      { wrapper },
    )
    expect(result.current.noted).toEqual([])

    act(() => result.current.register.mutate({ name: 'a', version: '1', agents: [] }))

    await waitFor(() => expect(result.current.noted).toEqual(['agent_packages']))
  })
})

describe('useNotedRestart', () => {
  it('forgets a noted restart once the service has restarted since', async () => {
    fetchMock.mockResolvedValue(jsonResponse(RESULT))
    const { result, rerender } = renderHook(
      ({ uptime }: { uptime: number | undefined }) => ({
        activate: useActivateVersion(),
        noted: useNotedRestart(uptime),
      }),
      { wrapper, initialProps: { uptime: 100_000 } },
    )
    act(() => result.current.activate.mutate({ name: 'a', version: '1' }))
    await waitFor(() => expect(result.current.noted).toEqual(['agent_packages']))

    // A service up for a shorter time than the note is old started after it.
    vi.spyOn(Date, 'now').mockReturnValue(Date.now() + 60_000)
    rerender({ uptime: 1 })

    expect(result.current.noted).toEqual([])
    vi.restoreAllMocks()
  })
})

describe('the other mutations', () => {
  it('activates a version with the files to overwrite', async () => {
    fetchMock.mockResolvedValue(jsonResponse(RESULT))
    const { result } = renderHook(() => useActivateVersion(), { wrapper })

    result.current.mutate({ name: 'acme', version: '1.1', keep: ['prompts/x'] })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/admin/api/agent-packages/acme/1.1/activate')
    expect(JSON.parse(init.body)).toEqual({ overwrite: [], keep: ['prompts/x'] })
  })

  it('deletes a version', async () => {
    fetchMock.mockResolvedValue({ ok: true, status: 204, json: async () => null } as Response)
    const { result } = renderHook(() => useDeleteVersion(), { wrapper })

    result.current.mutate({ name: 'acme', version: '1.0' })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(fetchMock.mock.calls[0][0]).toBe('/admin/api/agent-packages/acme/1.0')
    expect(fetchMock.mock.calls[0][1].method).toBe('DELETE')
  })

  it('removes a package', async () => {
    fetchMock.mockResolvedValue(jsonResponse(RESULT))
    const { result } = renderHook(() => useRemovePackage(), { wrapper })

    result.current.mutate('acme')
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(fetchMock.mock.calls[0][0]).toBe('/admin/api/agent-packages/acme')
    expect(fetchMock.mock.calls[0][1].method).toBe('DELETE')
  })
})

describe('packageErrorKey', () => {
  it('maps the status and detail code to a translation key', () => {
    expect(packageErrorKey(new ApiError('x', 403), { upload: true })).toBe(
      'packagesErrorUploadDisabled',
    )
    expect(packageErrorKey(new ApiError('Not an admin', 403))).toBe('packagesErrorForbidden')
    expect(
      packageErrorKey(
        new ApiError('Uploading ... is disabled (agent_packages.allow_upload).', 403),
      ),
    ).toBe('packagesErrorUploadDisabled')
    expect(packageErrorKey(new ApiError('x', 413))).toBe('packagesErrorTooLarge')
    expect(packageErrorKey(new ApiError('x', 422))).toBe('packagesErrorInvalid')
    expect(packageErrorKey(new ApiError('x', 404))).toBe('packagesErrorNotFound')
    expect(packageErrorKey(new ApiError('x', 409, 'busy'))).toBe('packagesErrorConflict')
    expect(packageErrorKey(new ApiError('x', 409, { code: 'default_dirs' }))).toBe(
      'packagesDefaultDirs',
    )
    expect(packageErrorKey(new ApiError('x', 409, { code: 'file_conflicts' }))).toBe(
      'packagesFileConflicts',
    )
    expect(packageErrorKey(new ApiError('x', 500))).toBe('packagesErrorGeneric')
    expect(packageErrorKey(new Error('offline'))).toBe('packagesErrorGeneric')
  })

  it('reads the conflict list from a file_conflicts detail only', () => {
    const conflicts = [{ path: 'prompts/de/x/prompt.yaml', current: 'a', incoming: 'b' }]
    expect(conflictsOf(new ApiError('x', 409, { code: 'file_conflicts', conflicts }))).toEqual(
      conflicts,
    )
    expect(conflictsOf(new ApiError('x', 409, { code: 'default_dirs' }))).toEqual([])
    expect(conflictsOf(null)).toEqual([])
  })
})
