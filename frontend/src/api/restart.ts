import { apiFetch } from './client'
import type { RestartResponse, StatusResponse } from './types'

/** Ask the service to restart in its process with the configuration on disk. */
export function requestRestart(): Promise<RestartResponse> {
  return apiFetch<RestartResponse>('/restart', { method: 'POST' })
}

const WILDCARDS = new Set(['0.0.0.0', '::', ''])
const LOOPBACK = new Set(['127.0.0.1', 'localhost', '::1', '[::1]'])

function sameHost(a: string, b: string): boolean {
  return a === b || (LOOPBACK.has(a) && LOOPBACK.has(b))
}

/**
 * The console's address after the restart, or null if it stays where this page
 * is. A wildcard bind keeps the host name the browser already uses.
 */
export function movedTo(target: RestartResponse, here: Location = window.location): string | null {
  const protocol = target.tls ? 'https:' : 'http:'
  const host = WILDCARDS.has(target.host) ? here.hostname : target.host
  const herePort = here.port || (here.protocol === 'https:' ? '443' : '80')
  if (
    protocol === here.protocol &&
    sameHost(host, here.hostname) &&
    String(target.port) === herePort
  ) {
    return null
  }
  const shownHost = host.includes(':') && !host.startsWith('[') ? `[${host}]` : host
  return `${protocol}//${shownHost}:${target.port}/admin/`
}

/**
 * Wait until the service on this page's address answers from a new run, i.e.
 * its `started_at` differs from `previous`. Errors while it is down are
 * expected and ignored. Resolves with the new status, or null after
 * `timeoutMs` or when `signal` aborts.
 */
export async function waitForRestart(
  previous: string,
  {
    intervalMs = 1000,
    timeoutMs = 90_000,
    signal,
  }: { intervalMs?: number; timeoutMs?: number; signal?: AbortSignal } = {},
): Promise<StatusResponse | null> {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline && !signal?.aborted) {
    await new Promise((resolve) => setTimeout(resolve, intervalMs))
    if (signal?.aborted) break
    try {
      const status = await apiFetch<StatusResponse>('/status', { signal })
      if (status.service.started_at !== previous) return status
    } catch {
      // Down while it restarts.
    }
  }
  return null
}
