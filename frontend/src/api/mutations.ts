import { useMutation, useQueryClient } from '@tanstack/react-query'
import type { Edits } from '../state/draft'
import { apiFetch } from './client'
import type {
  ApplyResponse,
  LintResponse,
  PreviewResponse,
  ProjectsResponse,
  PromptMessageDoc,
  PromptSaveResponse,
  RenderResponse,
} from './types'

/**
 * What applying the current draft would do — diff, validity, restart need.
 *
 * A rejected draft comes back as `valid: false` with issues, not as an HTTP
 * error: the dialog renders the reasons, so this is a successful answer to the
 * question asked.
 */
export function usePreview() {
  return useMutation({
    mutationFn: (edits: Edits) =>
      apiFetch<PreviewResponse>('/config/preview', {
        method: 'POST',
        body: JSON.stringify({ edits }),
      }),
  })
}

/**
 * Write the draft and reload the service.
 *
 * On success the saved config and the status both changed, so both queries are
 * invalidated — the pending-change count is measured against the saved config,
 * and leaving it stale would keep every just-applied edit counted as pending.
 */
export function useApply() {
  const queries = useQueryClient()
  return useMutation({
    mutationFn: (edits: Edits) =>
      apiFetch<ApplyResponse>('/config/apply', {
        method: 'POST',
        body: JSON.stringify({ edits }),
      }),
    onSuccess: () => {
      void queries.invalidateQueries({ queryKey: ['config'] })
      void queries.invalidateQueries({ queryKey: ['status'] })
    },
  })
}

/**
 * Re-read the TestBench project list and replace the server's cache.
 *
 * The response is written straight into the `projects` query rather than
 * invalidating it: an invalidation would refetch `GET /projects`, which returns
 * the very cache this call just replaced — a second round trip for an answer
 * already in hand.
 *
 * Never rejects on an unreachable TestBench: the route answers 200 with
 * `source: 'unavailable'`, and the screen shows that next to the list it kept.
 */
export function useRefreshProjects() {
  const queries = useQueryClient()
  return useMutation({
    mutationFn: () => apiFetch<ProjectsResponse>('/projects/refresh', { method: 'POST' }),
    onSuccess: (data) => queries.setQueryData(['projects'], data),
  })
}

/** Check one message body's Jinja syntax, for an editor gutter. */
export function useLintTemplate() {
  return useMutation({
    mutationFn: (content: string) =>
      apiFetch<LintResponse>('/prompts/lint', {
        method: 'POST',
        body: JSON.stringify({ content }),
      }),
  })
}

/** Render every message of a draft variant against sample vars and context. */
export function useRenderPrompt() {
  return useMutation({
    mutationFn: (body: {
      messages: PromptMessageDoc[]
      vars: Record<string, unknown>
      agent_context: Record<string, unknown>
    }) =>
      apiFetch<RenderResponse>('/prompts/render', {
        method: 'POST',
        body: JSON.stringify(body),
      }),
  })
}

/**
 * Write the edited prompt document back to disk.
 *
 * On success both the tree and the document are stale, since the file on disk
 * changed underneath them.
 */
export function useSavePrompt(lang: string, agent: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: unknown) =>
      apiFetch<PromptSaveResponse>(
        `/prompts/${encodeURIComponent(lang)}/${encodeURIComponent(agent)}`,
        { method: 'PUT', body: JSON.stringify(body) },
      ),
    onSuccess: () => {
      // The document on disk changed, so both the tree and the document are stale.
      queryClient.invalidateQueries({ queryKey: ['prompts'] })
    },
  })
}
