import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { useJob, useJobs } from './queries'
import { apiFetch } from './client'
import type { JobDetail, JobStatus, JobSummary } from './types'

vi.mock('./client', () => ({ apiFetch: vi.fn() }))

const fetchMock = vi.mocked(apiFetch)

const summary = (status: JobStatus): JobSummary => ({
  job_id: 'j1',
  agent_key: 'coverage_checker',
  project_key: 'p-1',
  project_name: 'Shop',
  root_key: null,
  item_ids: [],
  status,
  progress: null,
  error: null,
  warnings: [],
  report_type: null,
  created_at: '2026-10-13T10:00:00+00:00',
  updated_at: '2026-10-13T10:00:00+00:00',
  finished_at: null,
})

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

beforeEach(() => {
  fetchMock.mockReset()
  vi.useFakeTimers({ shouldAdvanceTime: true })
})

afterEach(() => vi.useRealTimers())

async function advance(ms: number) {
  await vi.advanceTimersByTimeAsync(ms)
}

describe.each([
  ['useJobs', () => useJobs({}), (s: JobStatus) => [summary(s)]],
  ['useJob', () => useJob('j1'), (s: JobStatus) => ({ ...summary(s), report: null }) as JobDetail],
] as const)('%s polling', (_name, useHook, payload) => {
  it('polls every 3 seconds while a job is running', async () => {
    fetchMock.mockResolvedValue(payload('running') as never)
    const { result } = renderHook(() => useHook(), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(fetchMock).toHaveBeenCalledTimes(1)

    await advance(3_100)
    expect(fetchMock).toHaveBeenCalledTimes(2)
    await advance(3_100)
    expect(fetchMock).toHaveBeenCalledTimes(3)
  })

  it.each(['succeeded', 'failed'] as const)('stops once the job is %s', async (status) => {
    fetchMock.mockResolvedValue(payload(status) as never)
    const { result } = renderHook(() => useHook(), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    await advance(10_000)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('stops polling after the job finishes', async () => {
    fetchMock
      .mockResolvedValueOnce(payload('running') as never)
      .mockResolvedValue(payload('succeeded') as never)
    const { result } = renderHook(() => useHook(), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    await advance(3_100)
    expect(fetchMock).toHaveBeenCalledTimes(2)
    await advance(10_000)
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })
})
