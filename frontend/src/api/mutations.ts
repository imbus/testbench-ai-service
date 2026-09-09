import { useMutation, useQueryClient } from '@tanstack/react-query'
import type { Edits } from '../state/draft'
import { apiFetch } from './client'
import type { ApplyResponse, PreviewResponse } from './types'

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
