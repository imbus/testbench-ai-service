import { renderHook, waitFor } from '@testing-library/react'
import { focusManager, QueryClient, QueryClientProvider } from '@tanstack/react-query'
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
  root_uid: null,
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
  // Same defaults as main.tsx, so per-hook overrides are what is tested.
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
  })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

beforeEach(() => {
  fetchMock.mockReset()
  vi.useFakeTimers({ shouldAdvanceTime: true })
})

afterEach(() => {
  focusManager.setFocused(undefined)
  vi.useRealTimers()
})

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
})

describe('useJob polling', () => {
  const detail = (s: JobStatus) => ({ ...summary(s), report: null }) as JobDetail

  it.each(['succeeded', 'failed'] as const)('stops once the job is %s', async (status) => {
    fetchMock.mockResolvedValue(detail(status) as never)
    const { result } = renderHook(() => useJob('j1'), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    await advance(30_000)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('stops polling after the job finishes', async () => {
    fetchMock
      .mockResolvedValueOnce(detail('running') as never)
      .mockResolvedValue(detail('succeeded') as never)
    const { result } = renderHook(() => useJob('j1'), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    await advance(3_100)
    expect(fetchMock).toHaveBeenCalledTimes(2)
    await advance(30_000)
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })
})

describe('useJobs idle refresh', () => {
  it.each([
    ['nothing runs', [summary('succeeded')]],
    ['the list is empty', []],
  ])('polls every 10 seconds when %s, so new jobs show up', async (_case, jobs) => {
    fetchMock.mockResolvedValue(jobs as never)
    const { result } = renderHook(() => useJobs({}), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    await advance(9_000)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    await advance(1_100)
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('falls back to the idle interval after the last job finishes', async () => {
    fetchMock
      .mockResolvedValueOnce([summary('running')] as never)
      .mockResolvedValue([summary('succeeded')] as never)
    const { result } = renderHook(() => useJobs({}), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    await advance(3_100)
    expect(fetchMock).toHaveBeenCalledTimes(2)
    await advance(9_000)
    expect(fetchMock).toHaveBeenCalledTimes(2)
    await advance(1_100)
    expect(fetchMock).toHaveBeenCalledTimes(3)
  })

  it('refetches when the window regains focus', async () => {
    fetchMock.mockResolvedValue([summary('succeeded')] as never)
    const { result } = renderHook(() => useJobs({}), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    focusManager.setFocused(false)
    focusManager.setFocused(true)
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
  })
})
