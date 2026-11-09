import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { JobViewApp, type JobViewConfig } from './JobViewApp'
import type { JobDetail } from '../api/types'
import { i18n } from '../i18n'

const JOB: JobDetail = {
  job_id: 'j1',
  agent_key: 'coverage_checker',
  project_key: 'p-1',
  project_name: 'Shop',
  root_key: 'REQ-1',
  root_uid: null,
  item_ids: [],
  status: 'failed',
  progress: null,
  error: 'TestBench unreachable',
  warnings: [],
  report_type: null,
  created_at: '2026-10-13T10:00:00+00:00',
  updated_at: '2026-10-13T10:01:00+00:00',
  finished_at: '2026-10-13T10:02:00+00:00',
  report: null,
}

function renderPage(config: JobViewConfig) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <JobViewApp config={config} />
    </QueryClientProvider>,
  )
}

function respond(status: number, body: unknown) {
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.resolve(new Response(JSON.stringify(body), { status }))),
  )
}

beforeEach(async () => {
  await i18n.changeLanguage('en')
})

afterEach(() => {
  vi.unstubAllGlobals()
})

test('shows the job as the console does, under the console header', async () => {
  respond(200, JOB)
  renderPage({ dataUrl: '/jobs/j1/view/data' })
  expect(await screen.findByRole('heading', { name: 'coverage_checker' })).toBeInTheDocument()
  expect(screen.getByText('TestBench unreachable')).toBeInTheDocument()
  expect(screen.getByText('AI Service')).toBeInTheDocument()
  expect(fetch).toHaveBeenCalledWith('/jobs/j1/view/data', expect.anything())
})

test('says the link expired without asking for the job', () => {
  respond(200, JOB)
  renderPage({ expired: true })
  expect(screen.getByText(/link has expired/)).toBeInTheDocument()
  expect(fetch).not.toHaveBeenCalled()
})

test('treats a 401 from the data as an expired link', async () => {
  respond(401, { detail: 'View expired' })
  renderPage({ dataUrl: '/jobs/j1/view/data' })
  expect(await screen.findByText(/link has expired/)).toBeInTheDocument()
})

test('reports other load failures', async () => {
  respond(503, { detail: 'down' })
  renderPage({ dataUrl: '/jobs/j1/view/data' })
  expect(await screen.findByText(/could not be loaded/)).toBeInTheDocument()
})

const SESSION = { username: 'anna', roles: [], is_admin: false, tb_server_url: 'x', has_user_key: true }

/** The job's data, plus the console's session endpoint answering *session* and *signIn*. */
function respondWithConsole(session: number, signIn = 200) {
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string, init?: RequestInit) => {
      if (url === '/admin/api/session') {
        const code = init?.method === 'POST' ? signIn : session
        const body = code === 200 ? SESSION : { detail: 'Invalid credentials' }
        return Promise.resolve(new Response(JSON.stringify(body), { status: code }))
      }
      return Promise.resolve(new Response(JSON.stringify(JOB), { status: 200 }))
    }),
  )
}

function stubAssign() {
  const assign = vi.fn()
  vi.stubGlobal('location', { ...window.location, assign })
  return assign
}

test('signed in to the console already, sign-in opens the job there', async () => {
  respondWithConsole(200)
  const assign = stubAssign()
  renderPage({ dataUrl: '/jobs/j1/view/data', consoleUrl: '/admin/jobs/j1' })
  await userEvent.click(await screen.findByRole('button', { name: 'Sign in' }))
  await vi.waitFor(() => expect(assign).toHaveBeenCalledWith('/admin/jobs/j1'))
  expect(screen.queryByLabelText('Password')).not.toBeInTheDocument()
})

test('signs in to the console on the page, then opens the job there', async () => {
  respondWithConsole(401)
  const assign = stubAssign()
  const user = userEvent.setup()
  renderPage({ dataUrl: '/jobs/j1/view/data', consoleUrl: '/admin/jobs/j1' })
  await user.click(await screen.findByRole('button', { name: 'Sign in' }))
  await user.type(await screen.findByLabelText('Username'), 'anna')
  await user.type(screen.getByLabelText('Password'), 'secret')
  await user.click(screen.getByRole('button', { name: 'Sign in with TestBench' }))
  await vi.waitFor(() => expect(assign).toHaveBeenCalledWith('/admin/jobs/j1'))
  expect(fetch).toHaveBeenCalledWith(
    '/admin/api/session',
    expect.objectContaining({ method: 'POST', body: JSON.stringify({ username: 'anna', password: 'secret' }) }),
  )
})

test('a failed sign-in stays on the page and says why', async () => {
  respondWithConsole(401, 401)
  const assign = stubAssign()
  const user = userEvent.setup()
  renderPage({ dataUrl: '/jobs/j1/view/data', consoleUrl: '/admin/jobs/j1' })
  await user.click(await screen.findByRole('button', { name: 'Sign in' }))
  await user.type(await screen.findByLabelText('Username'), 'anna')
  await user.type(screen.getByLabelText('Password'), 'wrong')
  await user.click(screen.getByRole('button', { name: 'Sign in with TestBench' }))
  expect(await screen.findByText('Wrong username or password.')).toBeInTheDocument()
  expect(assign).not.toHaveBeenCalled()
})

test('offers no sign-in when the console is switched off', async () => {
  respond(200, JOB)
  renderPage({ dataUrl: '/jobs/j1/view/data' })
  await screen.findByRole('heading', { name: 'coverage_checker' })
  expect(screen.queryByRole('button', { name: 'Sign in' })).not.toBeInTheDocument()
})
