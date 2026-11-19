/** The package cards' LLM client part: use a client as the provider, stop using it. */
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { PackagesResponse } from '../api/types'
import { usePackages } from '../api/packages'
import { i18n } from '../i18n'
import { AgentPackagesSection, usePackageDialogs } from './AgentPackages'
import { llmPkg, llmVersion, ok, packages, pkg } from './packages/fixtures'

beforeEach(() => i18n.changeLanguage('en'))

let fetchMock: ReturnType<typeof vi.fn>
let body: PackagesResponse

beforeEach(() => {
  body = packages({ packages: [llmPkg()] })
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? 'GET'
    if (url === '/admin/api/agent-packages' && method === 'GET') return ok(body)
    if (url === '/admin/api/config') return ok({ running: {}, disk: {}, config_path: 'c.toml' })
    if (method !== 'GET') {
      return ok({ written: ['config.toml'], backup: null, restart_required: ['agent_packages'] })
    }
    return ok({ detail: 'no' }, 404)
  })
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => vi.unstubAllGlobals())

function Section({ isAdmin }: { isAdmin: boolean }) {
  const list = usePackages()
  const dialogs = usePackageDialogs(list.data)
  return (
    <>
      <AgentPackagesSection packages={list} dialogs={dialogs} isAdmin={isAdmin} />
      {dialogs.element}
    </>
  )
}

function renderSection({ isAdmin = true } = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <Section isAdmin={isAdmin} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const IN_USE = () =>
  packages({
    packages: [llmPkg({ llm_client: 'acme_llm', versions: [llmVersion({ active: true })] })],
  })

describe('the LLM client of a package card', () => {
  it('lists the client and opens the provider dialog', async () => {
    const user = userEvent.setup()
    renderSection()

    const row = await screen.findByTestId('package-llm-client-acme_llm')
    expect(row).toHaveTextContent('acme_llm.client.AcmeClient')
    expect(screen.queryByText('The package declares no agents.')).not.toBeInTheDocument()
    expect(screen.queryByText('active LLM provider')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Use as LLM provider' }))

    expect(
      await screen.findByRole('heading', { name: 'Use the LLM client of acme-llm 1.0.0' }),
    ).toBeInTheDocument()
  })

  it('offers nothing to a non-admin', async () => {
    renderSection({ isAdmin: false })
    await screen.findByTestId('package-llm-client-acme_llm')
    expect(screen.queryByRole('button', { name: 'Use as LLM provider' })).not.toBeInTheDocument()
  })

  it('marks the package in use and stops using it', async () => {
    body = IN_USE()
    const user = userEvent.setup()
    renderSection()

    const card = await screen.findByTestId('package-acme-llm')
    expect(within(card).getAllByText('active LLM provider').length).toBeGreaterThan(0)
    expect(within(card).getByText('not loaded')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Use as LLM provider' })).not.toBeInTheDocument()
    // Removing is refused by the server while the client is in use.
    expect(screen.queryByRole('button', { name: 'Remove package' })).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Stop using as provider' }))
    const dialog = await screen.findByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: 'Stop using as provider' }))

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        '/admin/api/agent-packages/acme-llm/llm-client',
        expect.objectContaining({ method: 'DELETE' }),
      ),
    )
  })

  it('does not offer a version while another one is active', async () => {
    body = packages({
      packages: [
        llmPkg({
          versions: [llmVersion({ version: '2.0.0' }), llmVersion({ active: true })],
        }),
      ],
    })
    renderSection()

    const inactive = await screen.findByTestId('package-version-2.0.0')
    expect(
      within(inactive).queryByRole('button', { name: 'Use as LLM provider' }),
    ).not.toBeInTheDocument()
    const active = screen.getByTestId('package-version-1.0.0')
    expect(within(active).getByRole('button', { name: 'Use as LLM provider' })).toBeInTheDocument()
  })

  it('keeps an agent package without clients as it was', async () => {
    body = packages({ packages: [pkg()] })
    renderSection()
    await screen.findByTestId('package-acme-tb-agents')
    expect(screen.queryByRole('button', { name: 'Use as LLM provider' })).not.toBeInTheDocument()
    expect(screen.queryByText('LLM clients in 1.2.0')).not.toBeInTheDocument()
  })
})
