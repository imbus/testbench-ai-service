import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { i18n } from '../../i18n'
import { ProviderDialog } from './ProviderDialog'
import { llmVersion, ok } from './fixtures'

beforeEach(() => i18n.changeLanguage('en'))

let fetchMock: ReturnType<typeof vi.fn>

beforeEach(() => {
  fetchMock = vi.fn(async () =>
    ok({ written: ['config.toml'], backup: null, restart_required: ['agent_packages'] }),
  )
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => vi.unstubAllGlobals())

function renderDialog(version = llmVersion()) {
  const onClose = vi.fn()
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <ProviderDialog name="acme-llm" version={version} onClose={onClose} />
    </QueryClientProvider>,
  )
  return { onClose }
}

function posted(): { url: string; body: unknown } {
  const call = fetchMock.mock.calls.find(([, init]) => (init as RequestInit)?.method === 'POST')
  if (!call) throw new Error('nothing was posted')
  return { url: call[0] as string, body: JSON.parse((call[1] as RequestInit).body as string) }
}

const SUBMIT = { name: 'Use as LLM provider' }

describe('ProviderDialog', () => {
  it('sends the client, the models and the first model as the default', async () => {
    const user = userEvent.setup()
    const { onClose } = renderDialog()

    expect(screen.getByRole('button', SUBMIT)).toBeDisabled()
    await user.type(screen.getByLabelText('Model names'), 'acme-large\nacme-small, acme-tiny')
    await user.click(screen.getByRole('button', SUBMIT))

    await waitFor(() => expect(onClose).toHaveBeenCalled())
    expect(posted()).toEqual({
      url: '/admin/api/agent-packages/acme-llm/1.0.0/llm-client',
      body: {
        entry_point: 'acme_llm',
        models: ['acme-large', 'acme-small', 'acme-tiny'],
        default_model: 'acme-large',
      },
    })
  })

  it('leaves the default model alone when the box is unticked', async () => {
    const user = userEvent.setup()
    const { onClose } = renderDialog()

    await user.type(screen.getByLabelText('Model names'), 'acme-large')
    await user.click(screen.getByRole('checkbox'))
    await user.click(screen.getByRole('button', SUBMIT))

    await waitFor(() => expect(onClose).toHaveBeenCalled())
    expect(posted().body).toMatchObject({ models: ['acme-large'], default_model: null })
  })

  it.each(['gpt-acme', 'claude-acme', 'o3-acme'])(
    'refuses %s, which would never reach the client',
    async (model) => {
      const user = userEvent.setup()
      renderDialog()

      await user.type(screen.getByLabelText('Model names'), model)

      expect(screen.getByRole('alert')).toHaveTextContent(model)
      expect(screen.getByRole('button', SUBMIT)).toBeDisabled()
      expect(fetchMock).not.toHaveBeenCalled()
    },
  )

  it('offers a choice when the package has several clients', async () => {
    const base = llmVersion()
    const client = base.report.llm_clients!.acme_llm
    const version = llmVersion({
      report: {
        ...base.report,
        llm_clients: {
          acme_llm: client,
          acme_other: { ...client, class_path: 'acme_llm.other.Other' },
          acme_broken: { ...client, ok: false, errors: ['boom'] },
        },
      },
    })
    const user = userEvent.setup()
    renderDialog(version)

    expect(screen.getAllByRole('radio')).toHaveLength(2)
    await user.click(screen.getByRole('radio', { name: /acme_other/ }))
    await user.type(screen.getByLabelText('Model names'), 'acme-large')
    await user.click(screen.getByRole('button', SUBMIT))

    await waitFor(() => expect(posted().body).toMatchObject({ entry_point: 'acme_other' }))
  })

  it('shows why the server refused', async () => {
    fetchMock.mockResolvedValue(
      ok({ detail: { message: "'acme-large' is not a valid model name", issues: [] } }, 422),
    )
    const user = userEvent.setup()
    const { onClose } = renderDialog()

    await user.type(screen.getByLabelText('Model names'), 'acme-large')
    await user.click(screen.getByRole('button', SUBMIT))

    expect(await screen.findByRole('alert')).toHaveTextContent('The package was rejected.')
    expect(onClose).not.toHaveBeenCalled()
  })
})
