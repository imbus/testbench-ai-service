import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { i18n } from '../../i18n'
import { ActivateDialog, RegisterDialog } from './RegisterDialog'
import { ok, version } from './fixtures'

beforeEach(() => i18n.changeLanguage('en'))

const PROMPT = 'prompts/de/acme_risk_rater/prompt.yaml'
const TEMPLATE = 'templates/en/acme_risk_rater/template.html'
const CONFLICTS = [
  { path: PROMPT, current: 'name: mine', incoming: 'name: theirs' },
  { path: TEMPLATE, current: 'a', incoming: 'b' },
]
const RESULT = { written: ['config.toml'], backup: null, restart_required: ['agent_packages'] }

/**
 * The server's contract for differing files: each must be in `keep` or in
 * `overwrite`, never both; the undecided ones come back as a 409.
 */
async function server(_url: string, init: RequestInit) {
  const { overwrite = [], keep = [] } = JSON.parse(String(init.body))
  if (overwrite.some((path: string) => keep.includes(path)))
    return ok({ detail: { message: 'both', issues: [] } }, 422)
  const undecided = CONFLICTS.filter(
    ({ path }) => !overwrite.includes(path) && !keep.includes(path),
  )
  if (undecided.length > 0)
    return ok({ detail: { code: 'file_conflicts', message: 'x', conflicts: undecided } }, 409)
  return ok(RESULT)
}

let fetchMock: ReturnType<typeof vi.fn>

beforeEach(() => {
  fetchMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => vi.unstubAllGlobals())

function wrap(node: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>)
}

function bodies() {
  return fetchMock.mock.calls.map(([, init]) => JSON.parse(init.body))
}

describe('RegisterDialog', () => {
  it('blocks registering while the service uses the default folders', () => {
    wrap(
      <RegisterDialog
        name="acme-tb-agents"
        version={version()}
        registered={{}}
        defaultDirs
        onClose={() => {}}
      />,
    )

    expect(screen.getByText(/testbench-ai-service init --prompts-dir/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Register agents' })).toBeDisabled()
  })

  it('prefills key and endpoint, and leaves out agents that failed the check', async () => {
    fetchMock.mockResolvedValue(ok(RESULT))
    const onClose = vi.fn()
    const user = userEvent.setup()
    wrap(
      <RegisterDialog
        name="acme-tb-agents"
        version={version()}
        registered={{}}
        defaultDirs={false}
        onClose={onClose}
      />,
    )

    expect(screen.getByLabelText('risk_rater agent_key')).toHaveValue('risk_rater')
    expect(screen.getByLabelText('risk_rater endpoint_path')).toHaveValue('/acme-risk-rater')
    expect(screen.queryByLabelText('dup_finder agent_key')).toBeNull()
    expect(screen.getByTestId('not-registrable-dup_finder')).toHaveTextContent(
      'prompts/de/prompt.yaml is missing',
    )

    await user.clear(screen.getByLabelText('risk_rater agent_key'))
    await user.type(screen.getByLabelText('risk_rater agent_key'), 'acme_risk_rater')
    await user.click(screen.getByRole('button', { name: 'Register agents' }))

    await waitFor(() => expect(onClose).toHaveBeenCalled())
    expect(fetchMock.mock.calls[0][0]).toBe(
      '/admin/api/agent-packages/acme-tb-agents/1.2.0/register',
    )
    expect(bodies()[0]).toEqual({
      agents: [
        {
          entry_point: 'risk_rater',
          agent_key: 'acme_risk_rater',
          endpoint_path: '/acme-risk-rater',
          enabled: true,
        },
      ],
      overwrite: [],
      keep: [],
    })
  })

  it('asks for a choice per conflicting file and sends both lists', async () => {
    fetchMock.mockImplementation(server)
    const onClose = vi.fn()
    const user = userEvent.setup()
    wrap(
      <RegisterDialog
        name="acme-tb-agents"
        version={version()}
        registered={{}}
        defaultDirs={false}
        onClose={onClose}
      />,
    )
    const submit = () => screen.getByRole('button', { name: 'Register agents' })

    await user.click(submit())
    const replace = await screen.findByRole('radio', {
      name: `${PROMPT} replace with package version`,
    })
    expect(screen.getByText(/keep yours or replace it/)).toBeInTheDocument()
    // Nothing decided yet: the server would refuse again.
    expect(submit()).toBeDisabled()

    await user.click(screen.getByRole('button', { name: `View diff ${PROMPT}` }))
    const diff = screen.getByRole('dialog', { name: PROMPT })
    expect(within(diff).getByTestId('diff-current')).toHaveTextContent('name: mine')
    expect(within(diff).getByTestId('diff-incoming')).toHaveTextContent('name: theirs')
    await user.click(within(diff).getByRole('button', { name: 'Close' }))

    await user.click(replace)
    expect(submit()).toBeDisabled()
    await user.click(screen.getByRole('radio', { name: `${TEMPLATE} keep my file` }))
    await user.click(submit())

    await waitFor(() => expect(onClose).toHaveBeenCalled())
    expect(bodies()[1]).toMatchObject({ overwrite: [PROMPT], keep: [TEMPLATE] })
  })

  it('keeps the earlier choices when a retry reports another conflict', async () => {
    // The first answer names only the prompt; once that is decided, the
    // template turns up as well (the server lists what is undecided).
    fetchMock
      .mockResolvedValueOnce(
        ok({ detail: { code: 'file_conflicts', message: 'x', conflicts: [CONFLICTS[0]] } }, 409),
      )
      .mockImplementation(server)
    const onClose = vi.fn()
    const user = userEvent.setup()
    wrap(
      <RegisterDialog
        name="acme-tb-agents"
        version={version()}
        registered={{}}
        defaultDirs={false}
        onClose={onClose}
      />,
    )
    const submit = () => screen.getByRole('button', { name: 'Register agents' })

    await user.click(submit())
    await user.click(await screen.findByRole('radio', { name: `${PROMPT} keep my file` }))
    await user.click(submit())
    await user.click(
      await screen.findByRole('radio', { name: `${TEMPLATE} replace with package version` }),
    )
    expect(screen.getByRole('radio', { name: `${PROMPT} keep my file` })).toBeChecked()
    await user.click(submit())

    await waitFor(() => expect(onClose).toHaveBeenCalled())
    expect(bodies()[2]).toMatchObject({ overwrite: [TEMPLATE], keep: [PROMPT] })
  })

  it('shows a translated error with the server detail', async () => {
    fetchMock.mockResolvedValue(ok({ detail: 'acme_risk_rater is taken' }, 409))
    const user = userEvent.setup()
    wrap(
      <RegisterDialog
        name="acme-tb-agents"
        version={version()}
        registered={{}}
        defaultDirs={false}
        onClose={() => {}}
      />,
    )

    await user.click(screen.getByRole('button', { name: 'Register agents' }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('This conflicts with the current state of the package.')
    expect(alert).toHaveTextContent('acme_risk_rater is taken')
  })

  it('says so when every passing agent is registered already', () => {
    wrap(
      <RegisterDialog
        name="acme-tb-agents"
        version={version()}
        registered={{ acme_risk_rater: 'risk_rater' }}
        defaultDirs={false}
        onClose={() => {}}
      />,
    )

    expect(screen.getByText(/registered already/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Register agents' })).toBeDisabled()
  })
})

describe('ActivateDialog', () => {
  it('resolves file conflicts the same way', async () => {
    fetchMock.mockImplementation(server)
    const onClose = vi.fn()
    const user = userEvent.setup()
    wrap(
      <ActivateDialog
        name="acme-tb-agents"
        version="1.1.0"
        defaultDirs={false}
        onClose={onClose}
      />,
    )
    const submit = () => screen.getByRole('button', { name: 'Activate' })

    await user.click(submit())
    await user.click(
      await screen.findByRole('radio', { name: `${TEMPLATE} replace with package version` }),
    )
    expect(submit()).toBeDisabled()
    await user.click(screen.getByRole('radio', { name: `${PROMPT} keep my file` }))
    await user.click(submit())

    await waitFor(() => expect(onClose).toHaveBeenCalled())
    expect(bodies()[1]).toEqual({ overwrite: [TEMPLATE], keep: [PROMPT] })
  })

  it('blocks activating while the service uses the default folders', () => {
    wrap(<ActivateDialog name="acme-tb-agents" version="1.1.0" defaultDirs onClose={() => {}} />)

    expect(screen.getByText(/testbench-ai-service init --prompts-dir/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Activate' })).toBeDisabled()
  })
})
