import { ApiError, apiFetch } from './client'

const okResponse = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })

beforeEach(() => {
  document.cookie = 'tbai_admin_csrf=csrf-token-value; path=/'
  vi.restoreAllMocks()
})

test('prefixes the admin api path', async () => {
  const fetchMock = vi.fn().mockResolvedValue(okResponse({ ok: true }))
  vi.stubGlobal('fetch', fetchMock)
  await apiFetch('/status')
  expect(fetchMock.mock.calls[0][0]).toBe('/admin/api/status')
})

test('sends cookies with every request', async () => {
  const fetchMock = vi.fn().mockResolvedValue(okResponse({}))
  vi.stubGlobal('fetch', fetchMock)
  await apiFetch('/status')
  expect(fetchMock.mock.calls[0][1].credentials).toBe('same-origin')
})

test('attaches the CSRF header on mutating requests', async () => {
  const fetchMock = vi.fn().mockResolvedValue(okResponse({}))
  vi.stubGlobal('fetch', fetchMock)
  await apiFetch('/session', { method: 'DELETE' })
  const headers = new Headers(fetchMock.mock.calls[0][1].headers)
  expect(headers.get('X-CSRF-Token')).toBe('csrf-token-value')
})

test('omits the CSRF header on GET', async () => {
  const fetchMock = vi.fn().mockResolvedValue(okResponse({}))
  vi.stubGlobal('fetch', fetchMock)
  await apiFetch('/status')
  const headers = new Headers(fetchMock.mock.calls[0][1].headers)
  expect(headers.get('X-CSRF-Token')).toBeNull()
})

test('throws ApiError carrying the status and detail', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Invalid credentials' }), { status: 401 }),
    ),
  )
  await expect(apiFetch('/session', { method: 'POST' })).rejects.toMatchObject({
    status: 401,
    message: 'Invalid credentials',
  })
})

test('handles a 204 with no body', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 204 })))
  await expect(apiFetch('/session', { method: 'DELETE' })).resolves.toBeNull()
})

test('surfaces a network failure as an ApiError', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('failed to fetch')))
  await expect(apiFetch('/status')).rejects.toBeInstanceOf(ApiError)
})

test('uses string detail as the error message', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Custom error message' }), { status: 400 }),
    ),
  )
  await expect(apiFetch('/test')).rejects.toMatchObject({
    message: 'Custom error message',
    detail: 'Custom error message',
  })
})

test('uses object detail.message as error message and carries the full detail', async () => {
  const detailObj = { message: 'Validation failed', issues: [{ path: 'field', message: 'invalid' }] }
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: detailObj }), { status: 422 }),
    ),
  )
  await expect(apiFetch('/test')).rejects.toMatchObject({
    message: 'Validation failed',
    detail: detailObj,
  })
})

test('non-JSON error body uses fallback message and leaves detail undefined', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      new Response('Internal Server Error', { status: 500 }),
    ),
  )
  await expect(apiFetch('/test')).rejects.toMatchObject({
    message: 'Request failed with status 500',
    detail: undefined,
  })
})
