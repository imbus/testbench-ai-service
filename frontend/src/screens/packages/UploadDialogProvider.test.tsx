/** The upload wizard for a wheel that provides an LLM client. */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { i18n } from '../../i18n'
import { UploadDialog } from './UploadDialog'
import { llmPkg, llmVersion, ok, packages, version } from './fixtures'

beforeEach(() => i18n.changeLanguage('en'))

let fetchMock: ReturnType<typeof vi.fn>

beforeEach(() => {
  fetchMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => vi.unstubAllGlobals())

const WHEEL = new File(['wheel'], 'acme_llm-1.0.0-py3-none-any.whl')

async function upload(list = packages({ packages: [] }), kind: 'provider' | 'agents' = 'provider') {
  const onUseProvider = vi.fn()
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const user = userEvent.setup()
  render(
    <QueryClientProvider client={client}>
      <UploadDialog
        packages={list}
        kind={kind}
        onClose={vi.fn()}
        onActivate={vi.fn()}
        onUseProvider={onUseProvider}
      />
    </QueryClientProvider>,
  )
  await user.upload(screen.getByLabelText('Wheel file (.whl)'), WHEEL)
  await user.click(
    screen.getByRole('button', {
      name: kind === 'provider' ? 'Import provider wheel' : 'Import agent wheel',
    }),
  )
  return { user, onUseProvider }
}

describe('UploadDialog with an LLM client', () => {
  it('reports the client and hands over to the provider dialog', async () => {
    const uploaded = llmVersion()
    fetchMock.mockResolvedValue(ok(uploaded))
    const { user, onUseProvider } = await upload()

    const row = await screen.findByRole('row', { name: /acme_llm/ })
    expect(row).toHaveTextContent('LLM client')
    expect(row).toHaveTextContent('OK')
    expect(screen.queryByText('The package declares no agents.')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Next: register agents' })).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Next: use as LLM provider' }))

    expect(onUseProvider).toHaveBeenCalledWith(uploaded)
  })

  const MIXED = () => {
    const base = version({ active: false })
    return version({
      active: false,
      report: { ...base.report, llm_clients: llmVersion().report.llm_clients },
    })
  }

  it('offers only the provider step for a wheel with an agent and a client', async () => {
    fetchMock.mockResolvedValue(ok(MIXED()))
    await upload()

    expect(await screen.findByRole('button', { name: 'Next: use as LLM provider' })).toBeEnabled()
    expect(screen.queryByRole('button', { name: 'Next: register agents' })).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Upload LLM provider package' })).toBeInTheDocument()
  })

  it('offers only registering for the same wheel on the agents screen', async () => {
    fetchMock.mockResolvedValue(ok(MIXED()))
    await upload(undefined, 'agents')

    expect(await screen.findByRole('button', { name: 'Next: register agents' })).toBeEnabled()
    expect(
      screen.queryByRole('button', { name: 'Next: use as LLM provider' }),
    ).not.toBeInTheDocument()
  })

  it('says where a provider wheel went when it is uploaded on the agents screen', async () => {
    fetchMock.mockResolvedValue(ok(llmVersion()))
    await upload(undefined, 'agents')

    expect(await screen.findByText(/listed on the LLM provider screen/)).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: 'Next: use as LLM provider' }),
    ).not.toBeInTheDocument()
  })

  it('says where an agent wheel went when it is uploaded for the provider', async () => {
    fetchMock.mockResolvedValue(ok(version({ active: false })))
    await upload()

    expect(await screen.findByText(/listed on the Agents screen/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Next: register agents' })).not.toBeInTheDocument()
  })

  it('does not claim agents for a wheel whose report lists nothing', async () => {
    const base = version({ active: false })
    fetchMock.mockResolvedValue(ok(version({ active: false, report: { ...base.report, agents: {} } })))
    await upload()

    expect(
      await screen.findByText('The check found no agents and no LLM client in this package.'),
    ).toBeInTheDocument()
    expect(screen.queryByText(/listed on the Agents screen/)).not.toBeInTheDocument()
  })

  it('asks to activate first while another version is active', async () => {
    fetchMock.mockResolvedValue(ok(llmVersion({ version: '2.0.0' })))
    await upload(packages({ packages: [llmPkg({ versions: [llmVersion({ active: true })] })] }))

    expect(await screen.findByRole('button', { name: 'Activate' })).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: 'Next: use as LLM provider' }),
    ).not.toBeInTheDocument()
  })
})
