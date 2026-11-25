import { onTestFinished } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { Jobs } from './Jobs'
import type { JobDetail, JobSummary } from '../api/types'
import * as sessionState from '../state/session'
import { i18n } from '../i18n'

const base = {
  agent_key: 'coverage_checker',
  project_key: 'p-1',
  project_name: 'Shop',
  root_key: null,
  root_uid: null,
  item_ids: ['REQ-1'],
  warnings: [],
  report_type: null,
  created_at: '2026-10-13T10:00:00+00:00',
  updated_at: '2026-10-13T10:01:00+00:00',
}

const RUNNING: JobSummary = {
  ...base,
  job_id: 'j1',
  status: 'running',
  progress: { done: 3, total: 7, text: 'Interpreting sets' },
  error: null,
  finished_at: null,
}
const FAILED: JobSummary = {
  ...base,
  agent_key: 'link_finder',
  job_id: 'j2',
  status: 'failed',
  progress: null,
  error: 'TestBench unreachable',
  finished_at: '2026-10-13T10:02:00+00:00',
}

function detail(summary: JobSummary, extra: Partial<JobDetail> = {}): JobDetail {
  return { ...summary, report: null, ...extra }
}

let list: JobSummary[]
let details: Record<string, JobDetail>
const fetchMock = vi.fn((url: string) => {
  const match = /\/jobs\/(\w+)$/.exec(url)
  const body = match ? details[match[1]] : list
  return Promise.resolve(
    new Response(JSON.stringify(body), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
})

function Where() {
  const location = useLocation()
  return <div data-testid="where">{location.pathname + location.search}</div>
}

function renderJobs(path = '/admin/jobs') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/admin/jobs" element={<Jobs />} />
          <Route path="/admin/jobs/:jobId" element={<Jobs />} />
        </Routes>
        <Where />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

let hasUserKey: boolean

beforeEach(() => {
  hasUserKey = true
  vi.spyOn(sessionState, 'useSession').mockImplementation(
    () => ({ session: { has_user_key: hasUserKey } }) as never,
  )
  list = [RUNNING, FAILED]
  details = { j1: detail(RUNNING), j2: detail(FAILED) }
  fetchMock.mockClear()
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => vi.restoreAllMocks())

test('lists jobs with agent, status and progress', async () => {
  renderJobs()
  await waitFor(() => expect(screen.getByText('coverage_checker')).toBeInTheDocument())
  expect(screen.getByText('link_finder')).toBeInTheDocument()
  expect(screen.getByText('3/7')).toBeInTheDocument()
  const table = screen.getByRole('table')
  expect(within(table).getByText('Läuft')).toBeInTheDocument()
  expect(within(table).getByText('Fehlgeschlagen')).toBeInTheDocument()
})

test('the list shows item, project and start of each job', async () => {
  renderJobs()
  await screen.findByText('link_finder')
  for (const name of ['Agent', 'Element', 'Projekt', 'Gestartet', 'Status']) {
    expect(screen.getByRole('columnheader', { name })).toBeInTheDocument()
  }
  expect(screen.getAllByText('Shop')).toHaveLength(2)
})

test('selecting a job opens it on its own page without the list', async () => {
  renderJobs()
  await userEvent.click(await screen.findByText('link_finder'))
  await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent('/admin/jobs/j2'))
  const pane = await screen.findByTestId('job-detail')
  await waitFor(() => expect(within(pane).getByText('TestBench unreachable')).toBeInTheDocument())
  expect(screen.queryByText('coverage_checker')).not.toBeInTheDocument()
})

test('each job row is a real link to its job, keeping the filters', async () => {
  // A link rather than a selectable row: middle-click, Ctrl-click, "copy link"
  // and the status-bar URL all need an <a href>.
  list = [FAILED]
  renderJobs('/admin/jobs?status=failed')
  const link = await screen.findByRole('link', { name: 'link_finder' })
  expect(link).toHaveAttribute('href', '/admin/jobs/j2?status=failed')
})

test('the list shows how long each job took', async () => {
  list = [FAILED]
  renderJobs()
  await screen.findByText('link_finder')
  expect(screen.getByRole('columnheader', { name: 'Dauer' })).toBeInTheDocument()
  // 10:00:00 to 10:02:00
  expect(screen.getByText('2m 00s')).toBeInTheDocument()
})

test('the job table has no row selection', async () => {
  const { container } = renderJobs()
  await screen.findByText('link_finder')
  expect(container.querySelector('.p-selectable-row')).toBeNull()
})

test('a chosen filter is kept in the URL', async () => {
  renderJobs()
  await screen.findByText('link_finder')
  await userEvent.click(screen.getByRole('button', { name: 'Fehlgeschlagen' }))
  await waitFor(() =>
    expect(screen.getByTestId('where')).toHaveTextContent('/admin/jobs?status=failed'),
  )
})

test('the status chips show the chosen status, and All clears it', async () => {
  renderJobs('/admin/jobs?status=failed&agent=link_finder')
  const chips = await screen.findByRole('group', { name: 'Status' })
  expect(within(chips).getByRole('button', { name: 'Fehlgeschlagen' })).toHaveAttribute(
    'aria-pressed',
    'true',
  )
  expect(within(chips).getByRole('button', { name: 'Alle' })).toHaveAttribute(
    'aria-pressed',
    'false',
  )
  await userEvent.click(within(chips).getByRole('button', { name: 'Alle' }))
  await waitFor(() =>
    expect(screen.getByTestId('where')).toHaveTextContent(/^\/admin\/jobs\?agent=link_finder$/),
  )
  expect(within(chips).getByRole('button', { name: 'Alle' })).toHaveAttribute(
    'aria-pressed',
    'true',
  )
})

test('a filter in the URL is asked from the backend', async () => {
  renderJobs('/admin/jobs?agent=link_finder')
  await waitFor(() =>
    expect(
      fetchMock.mock.calls.some(([url]) => url.endsWith('/jobs?agent=link_finder&limit=50')),
    ).toBe(true),
  )
})

test('opening a job keeps the filters, and the back link returns to them', async () => {
  list = [FAILED]
  renderJobs('/admin/jobs?status=failed')
  await userEvent.click(await screen.findByText('link_finder'))
  await waitFor(() =>
    expect(screen.getByTestId('where')).toHaveTextContent('/admin/jobs/j2?status=failed'),
  )
  await userEvent.click(screen.getByRole('link', { name: /Alle Jobs/ }))
  expect(screen.getByTestId('where')).toHaveTextContent('/admin/jobs?status=failed')
})

test('newer and older step through the listed jobs', async () => {
  renderJobs('/admin/jobs/j1')
  const older = await screen.findByRole('button', { name: /Älterer Job/ })
  expect(screen.getByRole('button', { name: /Neuerer Job/ })).toBeDisabled()
  await waitFor(() => expect(older).toBeEnabled())
  await userEvent.click(older)
  await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent('/admin/jobs/j2'))
  await waitFor(() => expect(screen.getByRole('button', { name: /Älterer Job/ })).toBeDisabled())
  expect(screen.getByRole('button', { name: /Neuerer Job/ })).toBeEnabled()
})

test('opens the job named in the URL', async () => {
  renderJobs('/admin/jobs/j2')
  const pane = await screen.findByTestId('job-detail')
  await waitFor(() => expect(within(pane).getByText('TestBench unreachable')).toBeInTheDocument())
})

test('filtering by status asks the backend', async () => {
  renderJobs()
  await screen.findByText('link_finder')
  await userEvent.click(screen.getByRole('button', { name: 'Fehlgeschlagen' }))
  await waitFor(() =>
    expect(fetchMock.mock.calls.some(([url]) => url.endsWith('/jobs?status=failed&limit=50'))).toBe(
      true,
    ),
  )
})

test('an unknown report type is laid out from its shape, with the JSON a click away', async () => {
  const job = { ...FAILED, status: 'succeeded' as const, error: null, report_type: 'mystery' }
  list = [job]
  details = { j2: detail(job, { report: { answer: 42 } }) }
  renderJobs('/admin/jobs/j2')
  const pane = await screen.findByTestId('job-detail')
  await waitFor(() => expect(within(pane).getByText('Answer')).toBeInTheDocument())
  expect(within(pane).getByText('42')).toBeInTheDocument()
  expect(pane.querySelector('pre')).toBeNull()
  await userEvent.click(within(pane).getByRole('button', { name: 'JSON' }))
  expect(within(pane).getByText(/"answer": 42/)).toBeInTheDocument()
})

test('a link finder report gets its own view', async () => {
  const job = { ...FAILED, status: 'succeeded' as const, error: null, report_type: 'link_finder' }
  list = [job]
  const report = {
    requirement_key: 'REQ-1',
    aspects: {},
    candidates: [],
    sets_screened: 18,
    sets_detailed: 0,
    empty_sets: [],
    failed_sets: [],
    skipped_comments: [],
    reduced_mode: false,
    incomplete: false,
    set_paths: {},
  }
  details = { j2: detail(job, { report }) }
  renderJobs('/admin/jobs/j2')
  const pane = await screen.findByTestId('job-detail')
  await waitFor(() => expect(within(pane).getByTestId('link-summary')).toBeInTheDocument())
  expect(pane.querySelector('pre')).toBeNull()
})

test('shows warnings of a job', async () => {
  const job = {
    ...RUNNING,
    status: 'succeeded' as const,
    progress: null,
    warnings: ['Set S-7 locked'],
  }
  list = [job]
  details = { j1: detail(job) }
  renderJobs('/admin/jobs/j1')
  await waitFor(() => expect(screen.getByText('Set S-7 locked')).toBeInTheDocument())
})

test('an empty list shows the hint', async () => {
  list = []
  renderJobs()
  await waitFor(() => expect(screen.getByText('Noch keine Jobs.')).toBeInTheDocument())
})

test('a session without a TestBench user key explains why there are no jobs', async () => {
  list = []
  hasUserKey = false
  renderJobs()
  await waitFor(() =>
    expect(
      screen.getByText(
        'Diese Sitzung hat keinen TestBench-Benutzerschlüssel, daher gibt es keine Jobs.',
      ),
    ).toBeInTheDocument(),
  )
  expect(screen.queryByText('Noch keine Jobs.')).not.toBeInTheDocument()
})

test('a list row names its item by unique ID, falling back to the key', async () => {
  list = [
    { ...RUNNING, root_key: 'REQ-ROOT', root_uid: 'iTB-RQ-7', item_ids: ['x'] },
    { ...FAILED, root_key: 'REQ-OLD', root_uid: null, item_ids: ['y'] },
  ]
  renderJobs()
  expect(await screen.findByText('iTB-RQ-7')).toBeInTheDocument()
  expect(screen.queryByText('REQ-ROOT')).not.toBeInTheDocument()
  expect(screen.getByText('REQ-OLD')).toBeInTheDocument()
})

test('a list row names the requirement the job is for', async () => {
  list = [
    { ...RUNNING, root_key: 'REQ-ROOT', item_ids: ['x'] },
    { ...FAILED, root_key: null, item_ids: ['REQ-ITEM', 'REQ-2'] },
    { ...FAILED, job_id: 'j3', root_key: null, item_ids: [] },
  ]
  renderJobs()
  expect(await screen.findByText('REQ-ROOT')).toBeInTheDocument()
  expect(screen.getByText('REQ-ITEM')).toBeInTheDocument()
  expect(screen.queryByText('REQ-2')).not.toBeInTheDocument()
})

test('the detail header names the root key before the items', async () => {
  const job = { ...RUNNING, root_key: 'REQ-ROOT', item_ids: ['REQ-1'] }
  list = [job]
  details = { j1: detail(job) }
  renderJobs('/admin/jobs/j1')
  const pane = await screen.findByTestId('job-detail')
  await waitFor(() => expect(pane).toHaveTextContent('REQ-ROOT, REQ-1'))
})

describe('more jobs than one page', () => {
  const many = (count: number): JobSummary[] =>
    Array.from({ length: count }, (_, index) => ({ ...FAILED, job_id: `m${index}` }))
  const requestedLimits = () =>
    fetchMock.mock.calls
      .map(([url]) => /[?&]limit=(\d+)/.exec(String(url))?.[1])
      .filter((limit): limit is string => !!limit)

  test('a full page says that these are only the newest, and offers more', async () => {
    list = many(50)
    renderJobs()

    const more = await screen.findByTestId('jobs-more')
    expect(more).toHaveTextContent(i18n.t('jobsShowingNewest', { count: 50 }))
    expect(requestedLimits()).toContain('50')

    await userEvent.click(within(more).getByRole('button', { name: i18n.t('jobsShowMore') }))

    await waitFor(() => expect(requestedLimits()).toContain('100'))
  })

  test('a list shorter than the page ends without the hint', async () => {
    renderJobs()

    await screen.findByText('coverage_checker')
    expect(screen.queryByTestId('jobs-more')).not.toBeInTheDocument()
  })
})

describe('a job that is not there', () => {
  test('says so instead of reporting a failed load', async () => {
    const usual = fetchMock.getMockImplementation()!
    onTestFinished(() => void fetchMock.mockImplementation(usual))
    fetchMock.mockImplementation((url: string) =>
      Promise.resolve(
        /\/jobs\/\w+$/.test(url)
          ? new Response(JSON.stringify({ detail: 'Job not found' }), {
              status: 404,
              headers: { 'Content-Type': 'application/json' },
            })
          : new Response(JSON.stringify(list), {
              status: 200,
              headers: { 'Content-Type': 'application/json' },
            }),
      ),
    )
    renderJobs('/admin/jobs/doesnotexist')

    expect(await screen.findByText(i18n.t('jobNotFound'))).toBeInTheDocument()
    expect(screen.queryByText(i18n.t('jobsError'))).not.toBeInTheDocument()
  })
})

test('a failed job keeps the line breaks of its error', async () => {
  const job = { ...FAILED, error: 'first line\nsecond line' }
  list = [job]
  details = { j2: detail(job) }
  renderJobs('/admin/jobs/j2')

  const pane = await screen.findByTestId('job-detail')
  await waitFor(() => expect(pane.querySelector('.job-error-text')).not.toBeNull())
  expect(pane.querySelector('.job-error-text')?.textContent).toBe('first line\nsecond line')
})

test('the JSON view shows the stored text, not what the browser made of the numbers', async () => {
  const job = { ...FAILED, status: 'succeeded' as const, error: null, report_type: 'mystery' }
  list = [job]
  details = {
    j2: detail(job, {
      report: { big: 12345678901234567000 },
      report_json: '{\n  "big": 12345678901234567890\n}',
    }),
  }
  renderJobs('/admin/jobs/j2')
  const pane = await screen.findByTestId('job-detail')

  await userEvent.click(await within(pane).findByRole('button', { name: 'JSON' }))

  expect(within(pane).getByText(/"big": 12345678901234567890/)).toBeInTheDocument()
})
