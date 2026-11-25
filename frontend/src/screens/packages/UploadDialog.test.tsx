import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { i18n } from '../../i18n'
import { UploadDialog } from './UploadDialog'
import { ok, packages, pkg, version } from './fixtures'

beforeEach(() => i18n.changeLanguage('en'))

let fetchMock: ReturnType<typeof vi.fn>

beforeEach(() => {
  fetchMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => vi.unstubAllGlobals())

function renderDialog({
  list = packages({ packages: [] }),
  onActivate = vi.fn(),
  onClose = vi.fn(),
} = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <UploadDialog packages={list} onClose={onClose} onActivate={onActivate} />
    </QueryClientProvider>,
  )
  return { onActivate, onClose }
}

const WHEEL = new File(['wheel'], 'acme_tb_agents-1.2.0-py3-none-any.whl')

describe('UploadDialog', () => {
  it('uploads the wheel and shows the check report per agent', async () => {
    const uploaded = version({ active: false })
    fetchMock.mockResolvedValue(ok(uploaded))
    const user = userEvent.setup()
    renderDialog()

    expect(screen.getByRole('button', { name: 'Import agent wheel' })).toBeDisabled()
    await user.upload(screen.getByLabelText('Wheel file (.whl)'), WHEEL)
    await user.click(screen.getByRole('button', { name: 'Import agent wheel' }))

    expect(await screen.findByRole('row', { name: /dup_finder/ })).toHaveTextContent(
      'prompts/de/prompt.yaml is missing',
    )
    expect(screen.getByRole('row', { name: /risk_rater/ })).toHaveTextContent('OK')
    // The wizard has moved on to the report step.
    expect(screen.getByRole('table')).toBeInTheDocument()
    expect(screen.getByText(/acme-tb-agents 1.2.0 is uploaded/)).toBeInTheDocument()
  })

  it('registers the agents in its last step and closes', async () => {
    const uploaded = version({ active: false })
    fetchMock.mockResolvedValueOnce(ok(uploaded))
    const user = userEvent.setup()
    const { onClose } = renderDialog()

    await user.upload(screen.getByLabelText('Wheel file (.whl)'), WHEEL)
    await user.click(screen.getByRole('button', { name: 'Import agent wheel' }))
    await user.click(await screen.findByRole('button', { name: 'Next: register agents' }))

    // The report gave way to the register form; back returns to it.
    expect(screen.queryByRole('table')).toBeNull()
    expect(screen.getByLabelText('risk_rater agent_key')).toHaveValue('risk_rater')
    expect(screen.getByTestId('not-registrable-dup_finder')).toBeInTheDocument()

    fetchMock.mockResolvedValue(
      ok({ written: ['config.toml'], backup: null, restart_required: ['agent_packages'] }),
    )
    await user.click(screen.getByRole('button', { name: 'Register agents' }))
    await waitFor(() => expect(onClose).toHaveBeenCalled())
    const [url] = fetchMock.mock.calls[1]
    expect(url).toBe('/admin/api/agent-packages/acme-tb-agents/1.2.0/register')
  })

  it('goes back from the register step to the report', async () => {
    fetchMock.mockResolvedValue(ok(version({ active: false })))
    const user = userEvent.setup()
    renderDialog()

    await user.upload(screen.getByLabelText('Wheel file (.whl)'), WHEEL)
    await user.click(screen.getByRole('button', { name: 'Import agent wheel' }))
    await user.click(await screen.findByRole('button', { name: 'Next: register agents' }))
    await user.click(screen.getByRole('button', { name: 'Back' }))

    expect(screen.getByRole('table')).toBeInTheDocument()
  })

  it('hands over to activating when another version of the package is active', async () => {
    const uploaded = version({ version: '1.3.0', active: false })
    fetchMock.mockResolvedValue(ok(uploaded))
    const user = userEvent.setup()
    const { onActivate } = renderDialog({ list: packages({ packages: [pkg()] }) })

    await user.upload(screen.getByLabelText('Wheel file (.whl)'), WHEEL)
    await user.click(screen.getByRole('button', { name: 'Import agent wheel' }))

    expect(await screen.findByText(/Another version of acme-tb-agents is active/)).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Next: register agents' })).toBeNull()
    await user.click(screen.getByRole('button', { name: 'Activate' }))
    expect(onActivate).toHaveBeenCalledWith(uploaded)
  })

  it('opens the file chooser from its button', async () => {
    const user = userEvent.setup()
    renderDialog()
    const input = screen.getByLabelText('Wheel file (.whl)') as HTMLInputElement
    const click = vi.spyOn(input, 'click')

    await user.click(screen.getByRole('button', { name: 'Choose file…' }))

    expect(click).toHaveBeenCalled()
  })

  it('names the rejection and lists the server issues', async () => {
    fetchMock.mockResolvedValue(
      ok(
        {
          detail: {
            message: 'Not a wheel',
            issues: [{ path: 'METADATA', message: 'missing', toml_section: '' }],
          },
        },
        422,
      ),
    )
    const user = userEvent.setup()
    renderDialog()

    await user.upload(screen.getByLabelText('Wheel file (.whl)'), WHEEL)
    await user.click(screen.getByRole('button', { name: 'Import agent wheel' }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('The package was rejected.')
    expect(alert).toHaveTextContent('Not a wheel')
    expect(alert).toHaveTextContent('METADATA: missing')
  })

  it('names a file that is too large', async () => {
    fetchMock.mockResolvedValue(ok({ detail: { message: 'too big', issues: [] } }, 413))
    const user = userEvent.setup()
    renderDialog()

    await user.upload(screen.getByLabelText('Wheel file (.whl)'), WHEEL)
    await user.click(screen.getByRole('button', { name: 'Import agent wheel' }))

    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent('larger than the server accepts'),
    )
  })
})

describe('UploadDialog: what it says and offers after the upload', () => {
  async function uploadWith(
    uploaded: ReturnType<typeof version>,
    list = packages({ packages: [] }),
  ) {
    fetchMock.mockResolvedValue(ok(uploaded))
    const user = userEvent.setup()
    const handlers = renderDialog({ list })
    await user.upload(screen.getByLabelText('Wheel file (.whl)'), WHEEL)
    await user.click(screen.getByRole('button', { name: 'Import agent wheel' }))
    return { user, ...handlers }
  }

  it('says that a wheel it already knew is unchanged', async () => {
    const known = version({ active: false })
    await uploadWith(known, packages({ packages: [pkg({ versions: [known] })] }))

    expect(
      await screen.findByText(/acme-tb-agents 1\.2\.0 was already there and is unchanged/),
    ).toBeInTheDocument()
  })

  it('offers no registering when the package as a whole failed its check', async () => {
    const failed = version({ active: false })
    failed.report = { ...failed.report, ok: false, errors: ['requires nosuchlib>=1'] }
    await uploadWith(failed)

    expect(await screen.findByText(/does not pass the check/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Next: register agents' })).not.toBeInTheDocument()
  })

  it('still offers registering when only one entry point failed', async () => {
    await uploadWith(version({ active: false }))

    expect(await screen.findByRole('button', { name: 'Next: register agents' })).toBeEnabled()
  })

  it('cannot be closed while the wheel is being checked', async () => {
    let finish: (response: Response) => void = () => {}
    fetchMock.mockReturnValue(new Promise<Response>((resolve) => (finish = resolve)))
    const user = userEvent.setup()
    const { onClose } = renderDialog()
    await user.upload(screen.getByLabelText('Wheel file (.whl)'), WHEEL)
    await user.click(screen.getByRole('button', { name: 'Import agent wheel' }))

    for (const button of screen.getAllByRole('button', { name: 'Close' })) {
      expect(button).toBeDisabled()
    }
    await user.keyboard('{Escape}')
    expect(onClose).not.toHaveBeenCalled()
    expect(screen.getByText(/cannot be cancelled/)).toBeInTheDocument()

    finish(ok(version({ active: false })))
    await waitFor(() => expect(screen.getAllByRole('button', { name: 'Close' })[0]).toBeEnabled())
  })
})
