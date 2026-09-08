const BASE = '/admin/api'
const CSRF_COOKIE = 'tbai_admin_csrf'
const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS'])

export class ApiError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
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
    let detail = `Request failed with status ${response.status}`
    try {
      const body = await response.json()
      if (typeof body?.detail === 'string') detail = body.detail
    } catch {
      // A non-JSON error body leaves the default message in place.
    }
    throw new ApiError(detail, response.status)
  }

  if (response.status === 204) return null as T
  return (await response.json()) as T
}
