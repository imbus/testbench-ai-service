import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { DRAFT_STORAGE_KEY } from './draft'
import { SessionProvider, useSession } from './session'

const jsonResponse = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })

const wrapper = ({ children }: { children: ReactNode }) => (
  <SessionProvider>{children}</SessionProvider>
)

const session = {
  username: 'a.mueller',
  roles: ['test_manager'],
  is_admin: false,
  tb_server_url: 'https://tb.example.com:9443/api/',
}

beforeEach(() => {
  vi.restoreAllMocks()
  window.localStorage.clear()
})

test('recovers the session on mount', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(session)))
  const { result } = renderHook(() => useSession(), { wrapper })

  await waitFor(() => expect(result.current.loading).toBe(false))
  expect(result.current.session).toEqual(session)
})

test('a 401 on mount means not signed in, not an error', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(jsonResponse({ detail: 'Not authenticated' }, 401)),
  )
  const { result } = renderHook(() => useSession(), { wrapper })

  await waitFor(() => expect(result.current.loading).toBe(false))
  expect(result.current.session).toBeNull()
  expect(result.current.error).toBeNull()
})

test('loading starts true', () => {
  // Never resolves within this test: what matters is the value synchronously
  // after mount, before the mount request has any chance to settle.
  vi.stubGlobal('fetch', vi.fn().mockReturnValue(new Promise(() => {})))
  const { result } = renderHook(() => useSession(), { wrapper })

  expect(result.current.loading).toBe(true)
})

test('a failed sign-in leaves the form usable', async () => {
  vi.stubGlobal(
    'fetch',
    vi
      .fn()
      // Mount recovery: no existing session.
      .mockResolvedValueOnce(jsonResponse({ detail: 'Not authenticated' }, 401))
      // Sign-in attempt: bad credentials.
      .mockResolvedValueOnce(jsonResponse({ detail: 'Invalid credentials' }, 401)),
  )
  const { result } = renderHook(() => useSession(), { wrapper })
  await waitFor(() => expect(result.current.loading).toBe(false))

  await act(async () => {
    await result.current.signIn('a.mueller', 'wrong').catch(() => {})
  })

  expect(result.current.error).toBe('Invalid credentials')
  expect(result.current.busy).toBe(false)
})

test('a retried sign-in clears the previous error', async () => {
  vi.stubGlobal(
    'fetch',
    vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ detail: 'Not authenticated' }, 401))
      .mockResolvedValueOnce(jsonResponse({ detail: 'Invalid credentials' }, 401))
      .mockResolvedValueOnce(jsonResponse(session)),
  )
  const { result } = renderHook(() => useSession(), { wrapper })
  await waitFor(() => expect(result.current.loading).toBe(false))

  await act(async () => {
    await result.current.signIn('a.mueller', 'wrong').catch(() => {})
  })
  expect(result.current.error).toBe('Invalid credentials')

  await act(async () => {
    await result.current.signIn('a.mueller', 'secret')
  })

  expect(result.current.error).toBeNull()
  expect(result.current.session).toEqual(session)
})

test('signing out clears local state even if the request fails', async () => {
  vi.stubGlobal(
    'fetch',
    vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(session))
      .mockRejectedValueOnce(new TypeError('failed to fetch')),
  )
  const { result } = renderHook(() => useSession(), { wrapper })
  await waitFor(() => expect(result.current.session).toEqual(session))

  await act(async () => {
    await result.current.signOut().catch(() => {})
  })

  expect(result.current.session).toBeNull()
})

test('signing out clears the stored draft so another operator does not see queued edits', async () => {
  // Operator A queues edits.
  window.localStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify({ port: 9999 }))

  vi.stubGlobal(
    'fetch',
    vi
      .fn()
      // Mount recovery: session exists.
      .mockResolvedValueOnce(jsonResponse(session))
      // Sign-out: revoke the session.
      .mockResolvedValueOnce(jsonResponse({})),
  )
  const { result } = renderHook(() => useSession(), { wrapper })
  await waitFor(() => expect(result.current.session).toEqual(session))

  // Verify the draft is stored.
  expect(window.localStorage.getItem(DRAFT_STORAGE_KEY)).not.toBeNull()

  await act(async () => {
    await result.current.signOut()
  })

  // Operator A has signed out; the draft must be gone so Operator B cannot see it.
  expect(window.localStorage.getItem(DRAFT_STORAGE_KEY)).toBeNull()
})
