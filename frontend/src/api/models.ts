import { apiFetch } from './client'
import type { ModelCatalogue } from './types'

/**
 * Fetch the model catalogue, optionally scoped to a project.
 *
 * Split out from `useModels` (queries.ts) so `TestRunPanel` and its tests can
 * exercise the model picker without a network mock -- the query hook is the
 * thin, cached wrapper; this is the actual request.
 */
export function fetchModels(project?: string): Promise<ModelCatalogue> {
  const query = project ? `?project=${encodeURIComponent(project)}` : ''
  return apiFetch<ModelCatalogue>(`/models${query}`)
}
