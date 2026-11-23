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

let unauthorizedListener: (() => void) | null = null

/**
 * Be told when a request comes back 401, i.e. the console session has expired
 * or was revoked. The session state uses this to fall back to the login
 * screen instead of leaving every screen failing with "Not signed in".
 * `/session` itself is exempt: a 401 there is a failed sign-in or "not signed
 * in yet", which the session state handles on its own.
 */
export function setUnauthorizedListener(listener: (() => void) | null): void {
  unauthorizedListener = listener
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

  // A FormData body gets no explicit type: the browser sets the multipart one
  // with its boundary, which a hand-set header would lack.
  if (init.body && !(init.body instanceof FormData) && !headers.has('Content-Type')) {
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
    throw new ApiError(cause instanceof Error ? cause.message : 'Network request failed', 0)
  }

  if (response.status === 401 && path !== '/session') unauthorizedListener?.()

  if (!response.ok) {
    let message = `Request failed with status ${response.status}`
    let detailValue: unknown = undefined
    try {
      const body = await response.json()
      if (body?.detail !== undefined) {
        detailValue = body.detail
        if (typeof body.detail === 'string') {
          message = body.detail
        } else if (
          typeof body.detail === 'object' &&
          body.detail !== null &&
          'message' in body.detail &&
          typeof (body.detail as Record<string, unknown>).message === 'string'
        ) {
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
