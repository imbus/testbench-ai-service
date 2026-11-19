import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query'
import type { Translations } from '../i18n'
import { ApiError, apiFetch } from './client'
import type {
  FileConflict,
  PackagesResponse,
  PackageVersion,
  RegisterAgentRequest,
  RegisterResult,
} from './types'

const BASE = '/agent-packages'

function versionPath(name: string, version: string): string {
  return `${BASE}/${encodeURIComponent(name)}/${encodeURIComponent(version)}`
}

/** The uploaded packages, their versions and inspection reports. */
export function usePackages({ enabled = true }: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: ['packages'],
    queryFn: () => apiFetch<PackagesResponse>(BASE),
    enabled,
  })
}

// --- the restart a package change asks for ----------------------------------

// Not under ['packages']: invalidating the package list must not touch it.
const NOTED_KEY = ['restart-noted'] as const

interface NotedRestart {
  fields: string[]
  /** `Date.now()` of the latest note. */
  at: number
}

/**
 * Remember the restart a package change asks for.
 *
 * The restart banner otherwise derives from the config on disk, and a version
 * switch changes only the package manifest, so the server cannot tell from
 * config.toml that a restart is pending. Kept in the query cache, which every
 * screen shares and which goes away with the page.
 */
function noteRestart(queries: QueryClient, fields: string[]): void {
  if (fields.length === 0) return
  const previous = queries.getQueryData<NotedRestart>(NOTED_KEY)
  queries.setQueryData<NotedRestart>(NOTED_KEY, {
    fields: [...new Set([...(previous?.fields ?? []), ...fields])],
    at: Date.now(),
  })
}

/**
 * The restart fields package changes noted in this page, until the service has
 * restarted since: a service up for less time than the note is old took the
 * change up. `uptimeSeconds` is the status query's; undefined keeps the note.
 */
export function useNotedRestart(uptimeSeconds: number | undefined): string[] {
  const noted = useQuery<NotedRestart | null>({
    queryKey: NOTED_KEY,
    // Never fetched: the data only ever comes from `noteRestart`.
    queryFn: () => null,
    enabled: false,
    initialData: null,
    staleTime: Infinity,
  }).data
  if (!noted) return []
  if (uptimeSeconds !== undefined && Date.now() - uptimeSeconds * 1000 > noted.at) return []
  return noted.fields
}

// --- mutations ---------------------------------------------------------------

/** After a change: the packages, the config and the status (agents, restart) are stale. */
function useRefresh() {
  const queries = useQueryClient()
  return (result?: RegisterResult | null) => {
    if (result) noteRestart(queries, result.restart_required)
    void queries.invalidateQueries({ queryKey: ['packages'] })
    void queries.invalidateQueries({ queryKey: ['config'] })
    void queries.invalidateQueries({ queryKey: ['status'] })
    // An LLM client brings its own models, or takes them away again.
    void queries.invalidateQueries({ queryKey: ['models'] })
  }
}

/** Upload a wheel. The new version is inspected but not active yet. */
export function useUploadPackage() {
  const refresh = useRefresh()
  return useMutation({
    mutationFn: (file: File) => {
      const body = new FormData()
      body.append('file', file)
      return apiFetch<PackageVersion>(BASE, { method: 'POST', body })
    },
    onSuccess: () => refresh(),
  })
}

/** Configure entry points of a version as agents; this activates the version. */
export function useRegisterAgents() {
  const refresh = useRefresh()
  return useMutation({
    mutationFn: ({
      name,
      version,
      agents,
      overwrite = [],
      keep = [],
    }: {
      name: string
      version: string
      agents: RegisterAgentRequest[]
      /** Conflicting files the package version replaces. */
      overwrite?: string[]
      /** Conflicting files that stay as they are. */
      keep?: string[]
    }) =>
      apiFetch<RegisterResult>(`${versionPath(name, version)}/register`, {
        method: 'POST',
        body: JSON.stringify({ agents, overwrite, keep }),
      }),
    onSuccess: refresh,
  })
}

/** Make a version the active one; it is loaded at the next start. */
export function useActivateVersion() {
  const refresh = useRefresh()
  return useMutation({
    mutationFn: ({
      name,
      version,
      overwrite = [],
      keep = [],
    }: {
      name: string
      version: string
      overwrite?: string[]
      keep?: string[]
    }) =>
      apiFetch<RegisterResult>(`${versionPath(name, version)}/activate`, {
        method: 'POST',
        body: JSON.stringify({ overwrite, keep }),
      }),
    onSuccess: refresh,
  })
}

/** Delete an inactive version. */
export function useDeleteVersion() {
  const refresh = useRefresh()
  return useMutation({
    mutationFn: ({ name, version }: { name: string; version: string }) =>
      apiFetch<null>(versionPath(name, version), { method: 'DELETE' }),
    onSuccess: () => refresh(),
  })
}

/** Remove the agents of a package from the config and deactivate it. */
export function useRemovePackage() {
  const refresh = useRefresh()
  return useMutation({
    mutationFn: (name: string) =>
      apiFetch<RegisterResult>(`${BASE}/${encodeURIComponent(name)}`, { method: 'DELETE' }),
    onSuccess: refresh,
  })
}

/**
 * Make an LLM client of a version the service's custom provider; this
 * activates the version. `default_model` also becomes the default model.
 */
export function useUseLlmClient() {
  const refresh = useRefresh()
  return useMutation({
    mutationFn: ({
      name,
      version,
      entry_point,
      models,
      default_model = null,
    }: {
      name: string
      version: string
      entry_point: string
      models: string[]
      default_model?: string | null
    }) =>
      apiFetch<RegisterResult>(`${versionPath(name, version)}/llm-client`, {
        method: 'POST',
        body: JSON.stringify({ entry_point, models, default_model }),
      }),
    onSuccess: refresh,
  })
}

/** Stop using the LLM client of a package; the default provider takes over. */
export function useClearLlmClient() {
  const refresh = useRefresh()
  return useMutation({
    mutationFn: (name: string) =>
      apiFetch<RegisterResult>(`${BASE}/${encodeURIComponent(name)}/llm-client`, {
        method: 'DELETE',
      }),
    onSuccess: refresh,
  })
}

/**
 * Why a model name cannot belong to an uploaded LLM client, mirroring the
 * server's check: the client factory sends these names to OpenAI or Anthropic
 * whatever the configured provider is.
 */
export function modelNameProblem(model: string): 'reserved' | 'invalid' | null {
  if (/^(gpt-|claude-|o\d+)/.test(model)) return 'reserved'
  if (!/^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,127}$/.test(model)) return 'invalid'
  return null
}

// --- errors ------------------------------------------------------------------

function detailCode(detail: unknown): string | undefined {
  if (detail === null || typeof detail !== 'object') return undefined
  const code = (detail as { code?: unknown }).code
  return typeof code === 'string' ? code : undefined
}

/**
 * The translation for a failed package call. The backend's `detail` is English
 * only, so the console names the case by status and `detail.code`, and shows
 * the backend text as secondary information. A 403 means "uploading is off"
 * only for the upload call (or when the server says so); otherwise the session
 * lacks the admin role or has expired.
 */
export function packageErrorKey(
  error: unknown,
  { upload = false }: { upload?: boolean } = {},
): keyof Translations {
  if (!(error instanceof ApiError)) return 'packagesErrorGeneric'
  switch (error.status) {
    case 403:
      return upload || /allow_upload/.test(error.message)
        ? 'packagesErrorUploadDisabled'
        : 'packagesErrorForbidden'
    case 404:
      return 'packagesErrorNotFound'
    case 409: {
      const code = detailCode(error.detail)
      if (code === 'default_dirs') return 'packagesDefaultDirs'
      if (code === 'file_conflicts') return 'packagesFileConflicts'
      return 'packagesErrorConflict'
    }
    case 413:
      return 'packagesErrorTooLarge'
    case 422:
      return 'packagesErrorInvalid'
    default:
      return 'packagesErrorGeneric'
  }
}

/** The files a 409 `file_conflicts` answer lists; empty for anything else. */
export function conflictsOf(error: unknown): FileConflict[] {
  if (!(error instanceof ApiError) || detailCode(error.detail) !== 'file_conflicts') return []
  const conflicts = (error.detail as { conflicts?: unknown }).conflicts
  return Array.isArray(conflicts) ? (conflicts as FileConflict[]) : []
}

/** The messages of a 422 answer's `detail.issues`. */
export function issuesOf(error: unknown): string[] {
  if (!(error instanceof ApiError)) return []
  const detail = error.detail
  if (detail === null || typeof detail !== 'object') return []
  const issues = (detail as { issues?: unknown }).issues
  if (!Array.isArray(issues)) return []
  return issues
    .map((issue) => {
      if (issue === null || typeof issue !== 'object') return null
      const { path, message } = issue as { path?: unknown; message?: unknown }
      if (typeof message !== 'string') return null
      return typeof path === 'string' && path ? `${path}: ${message}` : message
    })
    .filter((entry): entry is string => entry !== null)
}
