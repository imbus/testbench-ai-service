import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { i18n } from '../../i18n'
import { UploadDialog } from './UploadDialog'
import { ok, version } from './fixtures'

beforeEach(() => i18n.changeLanguage('en'))

let fetchMock: ReturnType<typeof vi.fn>

beforeEach(() => {
  fetchMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => vi.unstubAllGlobals())

function renderDialog(onRegister = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <UploadDialog onClose={() => {}} onRegister={onRegister} />
    </QueryClientProvider>,
  )
  return onRegister
}

const WHEEL = new File(['wheel'], 'acme_tb_agents-1.2.0-py3-none-any.whl')

describe('UploadDialog', () => {
  it('uploads the wheel and shows the check report per agent', async () => {
    const uploaded = version({ active: false })
    fetchMock.mockResolvedValue(ok(uploaded))
    const user = userEvent.setup()
    const onRegister = renderDialog()

    expect(screen.getByRole('button', { name: 'Upload wheel' })).toBeDisabled()
    await user.upload(screen.getByLabelText('Wheel file (.whl)'), WHEEL)
    await user.click(screen.getByRole('button', { name: 'Upload wheel' }))

    expect(await screen.findByTestId('package-agent-dup_finder')).toHaveTextContent(
      'prompts/de/prompt.yaml is missing',
    )
    expect(screen.getByTestId('package-agent-risk_rater')).toBeInTheDocument()
    expect(screen.getByText(/acme-tb-agents 1.2.0 is uploaded/)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Register agents' }))
    expect(onRegister).toHaveBeenCalledWith(uploaded)
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
    await user.click(screen.getByRole('button', { name: 'Upload wheel' }))

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
    await user.click(screen.getByRole('button', { name: 'Upload wheel' }))

    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent('larger than the server accepts'),
    )
  })
})
