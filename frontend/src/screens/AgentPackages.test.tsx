/**
 * The agent package screen: uploaded wheels, their check reports, and the
 * register / activate / delete / remove actions (design §5.9).
 */
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { PackagesResponse } from '../api/types'
import { useNotedRestart, usePackages } from '../api/packages'
import { RestartBanner } from '../components/RestartBanner'
import { i18n } from '../i18n'
import { AgentPackagesSection, PackageUploadButton, usePackageDialogs } from './AgentPackages'
import { ok, packages, pkg, version } from './packages/fixtures'

beforeEach(() => i18n.changeLanguage('en'))

// Removing drops the overrides in the config FILE; the running config may lag
// behind it (Gamma's override was already removed on disk).
const CONFIG = {
  running: {
    projects: { Gamma: { agents: { acme_risk_rater: { enabled: true } } } },
  },
  disk: {
    agents: { acme_risk_rater: { package: 'acme-tb-agents', class_path: 'acme.risk:RiskRater' } },
    projects: {
      Alpha: { agents: { acme_risk_rater: { enabled: false } } },
      Beta: { agents: { other: { enabled: true } } },
    },
  },
  config_path: 'config.toml',
}

let fetchMock: ReturnType<typeof vi.fn>
let body: PackagesResponse

beforeEach(() => {
  body = packages()
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? 'GET'
    if (url === '/admin/api/agent-packages' && method === 'GET') return ok(body)
    if (url === '/admin/api/config') return ok(CONFIG)
    if (method === 'DELETE' && url.endsWith('/1.1.0')) return ok(null, 204)
    if (method !== 'GET') {
      return ok({ written: ['config.toml'], backup: null, restart_required: ['agent_packages'] })
    }
    return ok({ detail: 'no' }, 404)
  })
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => vi.unstubAllGlobals())

function Banner() {
  return <RestartBanner fields={useNotedRestart(undefined)} />
}

/** The parts the agents screen puts together: header button, section, dialogs. */
function AgentPackages({ isAdmin }: { isAdmin: boolean }) {
  const packages = usePackages()
  const dialogs = usePackageDialogs(packages.data)
  return (
    <>
      {isAdmin && <PackageUploadButton data={packages.data} dialogs={dialogs} />}
      <AgentPackagesSection packages={packages} dialogs={dialogs} isAdmin={isAdmin} />
      {dialogs.element}
    </>
  )
}

function renderScreen({ isAdmin = true }: { isAdmin?: boolean } = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <Banner />
        <AgentPackages isAdmin={isAdmin} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function calls(method: string) {
  return fetchMock.mock.calls.filter(([, init]) => (init?.method ?? 'GET') === method)
}

describe('agent packages screen', () => {
  it('disables the upload button and says how to turn uploading on', async () => {
    body = packages({ allow_upload: false })
    renderScreen()

    const button = await screen.findByRole('button', { name: 'Import agent wheel' })
    expect(button).toBeDisabled()
    expect(
      screen.getAllByText(/Set agent_packages.allow_upload = true in config.toml/).length,
    ).toBeGreaterThan(0)
  })

  it('shows the check report per agent, with the package warnings', async () => {
    renderScreen()

    const card = await screen.findByTestId('package-acme-tb-agents')
    const rater = within(card).getByTestId('package-agent-risk_rater')
    expect(rater).toHaveTextContent('acme_risk_rater')
    const finder = within(card).getByTestId('package-agent-dup_finder')
    expect(finder).toHaveTextContent('prompts/de/prompt.yaml is missing')
    expect(card).toHaveTextContent('Package warning: no README')
    expect(card).toHaveTextContent('3f9a0c1d')
  })

  it('marks a package that is not loaded, with the reason', async () => {
    body = packages({ packages: [pkg({ loaded: false, load_error: 'ImportError: acme' })] })
    renderScreen()

    const card = await screen.findByTestId('package-acme-tb-agents')
    expect(card).toHaveTextContent('not loaded')
    expect(card).toHaveTextContent('ImportError: acme')
  })

  it('offers activate and delete for an inactive version, register for the active one', async () => {
    body = packages({ packages: [pkg({ registered: {} })] })
    renderScreen()

    const active = await screen.findByTestId('package-version-1.2.0')
    expect(within(active).getByRole('button', { name: 'Register agents' })).toBeInTheDocument()
    expect(within(active).queryByRole('button', { name: 'Delete' })).toBeNull()
    const inactive = screen.getByTestId('package-version-1.1.0')
    expect(within(inactive).getByRole('button', { name: 'Activate' })).toBeInTheDocument()
    expect(within(inactive).getByRole('button', { name: 'Delete' })).toBeInTheDocument()
    expect(within(inactive).queryByRole('button', { name: 'Register agents' })).toBeNull()
  })

  it('shows no actions to a non-admin', async () => {
    renderScreen({ isAdmin: false })

    await screen.findByTestId('package-acme-tb-agents')
    for (const name of [
      'Import agent wheel',
      'Register agents',
      'Activate',
      'Delete',
      'Remove package',
    ])
      expect(screen.queryByRole('button', { name })).toBeNull()
  })

  it('activates a version and feeds the restart banner', async () => {
    const user = userEvent.setup()
    renderScreen()

    const inactive = await screen.findByTestId('package-version-1.1.0')
    await user.click(within(inactive).getByRole('button', { name: 'Activate' }))
    const dialog = screen.getByRole('dialog', { name: 'Activate acme-tb-agents 1.1.0' })
    await user.click(within(dialog).getByRole('button', { name: 'Activate' }))

    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('agent_packages'))
    const [url, init] = calls('POST')[0]
    expect(url).toBe('/admin/api/agent-packages/acme-tb-agents/1.1.0/activate')
    expect(JSON.parse(init.body)).toEqual({ overwrite: [], keep: [] })
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('deletes an inactive version after confirming', async () => {
    const user = userEvent.setup()
    renderScreen()

    const inactive = await screen.findByTestId('package-version-1.1.0')
    await user.click(within(inactive).getByRole('button', { name: 'Delete' }))
    const dialog = screen.getByRole('dialog', { name: 'Delete acme-tb-agents 1.1.0' })
    await user.click(within(dialog).getByRole('button', { name: 'Delete' }))

    await waitFor(() => expect(calls('DELETE')).toHaveLength(1))
    expect(calls('DELETE')[0][0]).toBe('/admin/api/agent-packages/acme-tb-agents/1.1.0')
  })

  it('names the agents and projects a removal touches, and that files stay', async () => {
    const user = userEvent.setup()
    renderScreen()

    await user.click(await screen.findByRole('button', { name: 'Remove package' }))
    const dialog = screen.getByRole('dialog', { name: 'Remove acme-tb-agents' })
    expect(dialog).toHaveTextContent('acme_risk_rater')
    expect(dialog).toHaveTextContent('Alpha')
    expect(dialog).not.toHaveTextContent('Beta')
    expect(dialog).not.toHaveTextContent('Gamma')
    expect(dialog).toHaveTextContent(
      'Prompt and template files and the uploaded versions are kept.',
    )

    await user.click(within(dialog).getByRole('button', { name: 'Remove package' }))
    await waitFor(() => expect(calls('DELETE')).toHaveLength(1))
    expect(calls('DELETE')[0][0]).toBe('/admin/api/agent-packages/acme-tb-agents')
  })

  it('opens the register dialog for the active version', async () => {
    const user = userEvent.setup()
    body = packages({ packages: [pkg({ registered: {} })] })
    renderScreen()

    const active = await screen.findByTestId('package-version-1.2.0')
    await user.click(within(active).getByRole('button', { name: 'Register agents' }))

    expect(
      screen.getByRole('dialog', { name: 'Register agents of acme-tb-agents 1.2.0' }),
    ).toBeInTheDocument()
  })

  it('offers no register when every agent that passed is registered already', async () => {
    // The fixture registers risk_rater; dup_finder failed its check.
    renderScreen()

    const active = await screen.findByTestId('package-version-1.2.0')
    expect(within(active).queryByRole('button', { name: 'Register agents' })).toBeNull()
    expect(screen.getByRole('button', { name: 'Remove package' })).toBeInTheDocument()
  })

  it('offers register for a version when no version is active', async () => {
    body = packages({
      packages: [pkg({ registered: {}, versions: [version({ active: false })] })],
    })
    renderScreen()

    const only = await screen.findByTestId('package-version-1.2.0')
    expect(within(only).getByRole('button', { name: 'Register agents' })).toBeInTheDocument()
    expect(within(only).getByRole('button', { name: 'Delete' })).toBeInTheDocument()
  })
})
