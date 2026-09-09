import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { DRAFT_STORAGE_KEY, DraftProvider } from '../state/draft'
import { DiffDialog } from './DiffDialog'

const fetchMock = vi.fn()

function jsonResponse(body: unknown, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as Response
}

const PREVIEW_OK = {
  valid: true,
  issues: [],
  diffs: [
    {
      path: '/tmp/config.toml',
      diff: '--- /tmp/config.toml\n+++ /tmp/config.toml\n-port = 8010\n+port = 9999\n',
      added: 1,
      removed: 1,
    },
  ],
  restart_required: ['port'],
  in_flight_tasks: 0,
  toml: '[testbench-ai-service]\nport = 9999\n',
}

function renderDialog(onClose = vi.fn()) {
  window.localStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify({ port: 9999 }))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <DraftProvider saved={{ port: 8010 }}>
        <DiffDialog lang="en" onClose={onClose} />
      </DraftProvider>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  window.localStorage.clear()
  vi.stubGlobal('fetch', fetchMock)
  document.cookie = 'tbai_admin_csrf=token-123'
  fetchMock.mockReset()
})

describe('DiffDialog', () => {
  it('previews on open and shows the diff', async () => {
    fetchMock.mockResolvedValue(jsonResponse(PREVIEW_OK))

    renderDialog()

    expect(await screen.findByText(/-port = 8010/)).toBeInTheDocument()
    expect(screen.getByText(/\+port = 9999/)).toBeInTheDocument()
  })

  it('names the file it would write', async () => {
    fetchMock.mockResolvedValue(jsonResponse(PREVIEW_OK))

    renderDialog()

    expect(await screen.findByText(/\/tmp\/config\.toml/)).toBeInTheDocument()
  })

  it('warns that the change needs a restart', async () => {
    fetchMock.mockResolvedValue(jsonResponse(PREVIEW_OK))

    renderDialog()

    await screen.findByText(/Needs a restart:/)
    // Scoped to the restart line: /port/ alone also matches the diff body,
    // and Testing Library throws on multiple matches.
    expect(screen.getByText(/Needs a restart:/).textContent).toContain('port')
  })

  it('applies and closes on success', async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(PREVIEW_OK))
      .mockResolvedValueOnce(
        jsonResponse({
          written: ['/tmp/config.toml'],
          backup: '/tmp/config.toml.bak',
          restart_required: [],
          reloaded: true,
          in_flight_tasks: 0,
        }),
      )
    const onClose = vi.fn()
    renderDialog(onClose)

    await screen.findByText(/-port = 8010/)
    await userEvent.click(screen.getByRole('button', { name: 'Apply' }))

    await waitFor(() => expect(onClose).toHaveBeenCalled())
    expect(fetchMock.mock.calls[1][0]).toBe('/admin/api/config/apply')
  })

  it('clears the draft after a successful apply', async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(PREVIEW_OK))
      .mockResolvedValueOnce(
        jsonResponse({
          written: ['/tmp/config.toml'],
          backup: null,
          restart_required: [],
          reloaded: true,
          in_flight_tasks: 0,
        }),
      )
    renderDialog()

    await screen.findByText(/-port = 8010/)
    await userEvent.click(screen.getByRole('button', { name: 'Apply' }))

    await waitFor(() =>
      expect(window.localStorage.getItem(DRAFT_STORAGE_KEY)).toBeNull(),
    )
  })

  it('shows the validation issues and offers no apply when the draft is invalid', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        valid: false,
        issues: [
          { path: 'port', message: 'Input should be a valid integer', toml_section: '[x]' },
        ],
        diffs: [],
        restart_required: [],
        in_flight_tasks: 0,
        toml: '',
      }),
    )

    renderDialog()

    expect(await screen.findByText(/Input should be a valid integer/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Apply' })).not.toBeInTheDocument()
  })

  it('warns about in-flight agent runs', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ ...PREVIEW_OK, in_flight_tasks: 2 }))

    renderDialog()

    expect(await screen.findByText(/2 agent runs are still in flight/)).toBeInTheDocument()
  })

  it('closes without applying', async () => {
    fetchMock.mockResolvedValue(jsonResponse(PREVIEW_OK))
    const onClose = vi.fn()
    renderDialog(onClose)

    await screen.findByText(/-port = 8010/)
    await userEvent.click(screen.getByRole('button', { name: 'Close' }))

    expect(onClose).toHaveBeenCalled()
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('reports a failed apply and keeps the dialog open', async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(PREVIEW_OK))
      .mockResolvedValueOnce(jsonResponse({ detail: 'Cannot write /tmp/config.toml' }, 400))
    const onClose = vi.fn()
    renderDialog(onClose)

    await screen.findByText(/-port = 8010/)
    await userEvent.click(screen.getByRole('button', { name: 'Apply' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Cannot write /tmp/config.toml')
    expect(onClose).not.toHaveBeenCalled()
  })
})
