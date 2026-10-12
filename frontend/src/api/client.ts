const BASE = '/admin/api'
const CSRF_COOKIE = 'tbai_admin_csrf'
const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS'])

export class ApiError extends Error {
  readonly status: number
  readonly detail: unknown

  constructor(message: string, status: number, detail?: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

function readCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`))
  return match ? decodeURIComponent(match[1]) : null
}

/**
 * Call the console API.
 *
 * The session cookie is httpOnly, so it travels automatically; the CSRF token is
 * readable by design and echoed back on anything that changes state.
 */
export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? 'GET').toUpperCase()
  const headers = new Headers(init.headers)

  if (init.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  if (!SAFE_METHODS.has(method)) {
    const csrf = readCookie(CSRF_COOKIE)
    if (csrf) headers.set('X-CSRF-Token', csrf)
  }

  let response: Response
  try {
    response = await fetch(`${BASE}${path}`, {
      ...init,
      method,
      headers,
      credentials: 'same-origin',
    })
  } catch (cause) {
    throw new ApiError(
      cause instanceof Error ? cause.message : 'Network request failed',
      0,
    )
  }

  if (!response.ok) {
    let message = `Request failed with status ${response.status}`
    let detailValue: unknown = undefined
    try {
      const body = await response.json()
      if (body?.detail !== undefined) {
        detailValue = body.detail
        if (typeof body.detail === 'string') {
          message = body.detail
        } else if (typeof body.detail === 'object' && body.detail !== null && 'message' in body.detail && typeof (body.detail as Record<string, unknown>).message === 'string') {
          message = (body.detail as Record<string, unknown>).message as string
        }
      }
    } catch {
      // A non-JSON error body leaves the default message in place.
    }
    throw new ApiError(message, response.status, detailValue)
  }

  if (response.status === 204) return null as T
  return (await response.json()) as T
}
