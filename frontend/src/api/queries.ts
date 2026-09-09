import { useQuery } from '@tanstack/react-query'
import { apiFetch } from './client'
import type { ConfigResponse, LogLine, MetaResponse, StatusResponse } from './types'

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
