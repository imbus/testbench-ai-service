/** The LLM screen's section for uploaded packages that provide an LLM client. */
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { PackagesResponse } from '../../api/types'
import { i18n } from '../../i18n'
import { ProviderPackagesSection } from './ProviderPackagesSection'
import { llmPkg, llmVersion, ok, packages, pkg } from './fixtures'

beforeEach(() => i18n.changeLanguage('en'))

let body: PackagesResponse
let status: Record<string, unknown>

beforeEach(() => {
  body = packages({ packages: [pkg(), llmPkg()] })
  status = {}
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      if (url === '/admin/api/agent-packages') return ok(body)
      if (url === '/admin/api/status') return ok(status)
      return ok({ running: {}, disk: {}, config_path: 'c.toml' })
    }),
  )
})

afterEach(() => vi.unstubAllGlobals())

function renderSection({ isAdmin = true } = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ProviderPackagesSection isAdmin={isAdmin} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('ProviderPackagesSection', () => {
  it('lists only the packages that provide an LLM client', async () => {
    renderSection()

    const section = await screen.findByRole('region', { name: 'Upload custom LLM provider' })
    expect(await within(section).findByTestId('package-acme-llm')).toBeInTheDocument()
    expect(within(section).queryByTestId('package-acme-tb-agents')).not.toBeInTheDocument()
  })

  it('says so when no package provides one', async () => {
    body = packages({ packages: [pkg()] })
    renderSection()
    expect(
      await screen.findByText('No package with an LLM client has been uploaded yet.'),
    ).toBeInTheDocument()
  })

  it('opens the upload wizard and the provider dialog for an admin', async () => {
    const user = userEvent.setup()
    renderSection()

    await user.click(await screen.findByRole('button', { name: 'Use as LLM provider' }))
    expect(
      await screen.findByRole('heading', { name: 'Use the LLM client of acme-llm 1.0.0' }),
    ).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Cancel' }))

    await user.click(screen.getByRole('button', { name: 'Import provider wheel' }))
    expect(await screen.findByLabelText('Wheel file (.whl)')).toBeInTheDocument()
  })

  it('shows a non-admin the packages without any action', async () => {
    renderSection({ isAdmin: false })
    await screen.findByTestId('package-acme-llm')
    expect(screen.queryByRole('button', { name: 'Import provider wheel' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Use as LLM provider' })).not.toBeInTheDocument()
  })

  it('names why the client in use is not running', async () => {
    body = packages({
      packages: [llmPkg({ llm_client: 'acme_llm', versions: [llmVersion({ active: true })] })],
    })
    status = { llm_client_error: 'Not loaded yet. Restart the service to load it.' }
    renderSection()

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('The LLM client of the uploaded package is not in use')
    expect(alert).toHaveTextContent('Not loaded yet. Restart the service to load it.')
  })
})
