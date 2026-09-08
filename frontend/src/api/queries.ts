import { useQuery } from '@tanstack/react-query'
import { apiFetch } from './client'
import type { MetaResponse } from './types'

/** Unauthenticated: lets the login screen name the TestBench server. */
export function useMeta() {
  return useQuery({
    queryKey: ['meta'],
    queryFn: () => apiFetch<MetaResponse>('/meta'),
    staleTime: Infinity,
  })
}
