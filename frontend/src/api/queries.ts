import { useQuery } from '@tanstack/react-query'
import { apiFetch } from './client'
import type {
  ConfigResponse,
  LogLine,
  MetaResponse,
  ModelCatalogue,
  ProjectsResponse,
  PromptDocument,
  PromptMeta,
  PromptTreeResponse,
  StatusResponse,
} from './types'

/** Unauthenticated: lets the login screen name the TestBench server. */
export function useMeta() {
  return useQuery({
    queryKey: ['meta'],
    queryFn: () => apiFetch<MetaResponse>('/meta'),
    staleTime: Infinity,
  })
}

export function useStatus({ enabled = true }: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: ['status'],
    queryFn: () => apiFetch<StatusResponse>('/status'),
    refetchInterval: 15_000,
    enabled,
  })
}

export function useLogs(limit = 25) {
  return useQuery({
    queryKey: ['logs', limit],
    queryFn: () => apiFetch<LogLine[]>(`/logs?limit=${limit}`),
    refetchInterval: 15_000,
  })
}

export function useConfig({ enabled = true }: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: ['config'],
    queryFn: () => apiFetch<ConfigResponse>('/config'),
    enabled,
  })
}

/**
 * The TestBench project list the server cached at login.
 *
 * Deliberately not polled. The server fetches once per session and only
 * re-reads on an explicit `POST /projects/refresh`, because the stored token
 * may be the operator's plaintext password; an interval here would spend it
 * over and over for a list that cannot have changed server-side.
 */
export function useProjects({ enabled = true }: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: ['projects'],
    queryFn: () => apiFetch<ProjectsResponse>('/projects'),
    staleTime: Infinity,
    enabled,
  })
}

/**
 * Variant names and variable declarations for one agent's prompt.
 *
 * `file` carries the prompt the *draft* points at — a project's override, or a
 * switch the operator has made in the form but not yet applied — so the form
 * re-reads the new file's variants before the change is written. Without it a
 * project pointing at a different prompt would be edited against the global
 * prompt's declarations, which is wrong metadata with no symptom until the
 * agent runs.
 *
 * Every segment is percent-encoded: agent keys and languages come from config
 * keys, which are operator-controlled, and an unencoded `/` would silently
 * address a different route.
 *
 * A 404 (no such prompt file) is a real answer the form renders around, so it
 * is surfaced rather than retried.
 */
export function usePromptMeta(
  lang: string,
  agent: string,
  file?: string,
  { enabled = true }: { enabled?: boolean } = {},
) {
  const query = file ? `?file=${encodeURIComponent(file)}` : ''
  return useQuery({
    queryKey: ['prompt-meta', lang, agent, file ?? null],
    queryFn: () =>
      apiFetch<PromptMeta>(
        `/prompts/${encodeURIComponent(lang)}/${encodeURIComponent(agent)}/meta${query}`,
      ),
    staleTime: Infinity,
    retry: false,
    // An empty agent key is a guaranteed 404: agent detail renders before a
    // scope is settled, and asking anyway would 404 on every such render.
    enabled: enabled && !!lang && !!agent,
  })
}

/**
 * The model catalogue, optionally scoped to a project.
 *
 * With a project, `key_present` reflects the project variable OR the global
 * one — matching the backend's silent credential fallback, so the answer is
 * "will a run find a key at all".
 */
export function useModels(
  project?: string,
  { enabled = true }: { enabled?: boolean } = {},
) {
  const query = project ? `?project=${encodeURIComponent(project)}` : ''
  return useQuery({
    queryKey: ['models', project ?? null],
    queryFn: () => apiFetch<ModelCatalogue>(`/models${query}`),
    staleTime: Infinity,
    enabled,
  })
}

/** The full prompt tree, grouped by language, for the prompt editor's browser. */
export function usePromptTree() {
  return useQuery({
    queryKey: ['prompts', 'tree'],
    queryFn: () => apiFetch<PromptTreeResponse>('/prompts'),
  })
}

/**
 * The full editable prompt document -- every variant, every message body.
 *
 * Every segment is percent-encoded, matching `usePromptMeta`. A 404 (no such
 * prompt file) is a real answer the editor renders around, so it is surfaced
 * rather than retried.
 */
export function usePromptDocument(lang: string | undefined, agent: string | undefined) {
  return useQuery({
    queryKey: ['prompts', 'doc', lang, agent],
    queryFn: () =>
      apiFetch<PromptDocument>(
        `/prompts/${encodeURIComponent(lang!)}/${encodeURIComponent(agent!)}`,
      ),
    enabled: Boolean(lang && agent),
    retry: false,
  })
}
