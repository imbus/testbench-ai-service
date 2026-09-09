import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { DraftProvider } from '../state/draft'
import { Raw } from './Raw'

const fetchMock = vi.fn()
const TOML = '[testbench-ai-service]\nport = 9999\n'

function renderRaw() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <DraftProvider saved={{ port: 8010 }}>
        <Raw lang="en" />
      </DraftProvider>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  window.localStorage.clear()
  vi.stubGlobal('fetch', fetchMock)
  document.cookie = 'tbai_admin_csrf=token-123'
  fetchMock.mockReset()
  fetchMock.mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({
      valid: true,
      issues: [],
      diffs: [],
      restart_required: [],
      in_flight_tasks: 0,
      toml: TOML,
    }),
  } as Response)
})

describe('Raw', () => {
  it('shows the generated config.toml', async () => {
    renderRaw()

    expect(await screen.findByText(/port = 9999/)).toBeInTheDocument()
  })

  it('says the view is read-only and generated', async () => {
    renderRaw()

    expect(
      await screen.findByText('Generated from the current (unapplied) state · read-only'),
    ).toBeInTheDocument()
  })

  it('offers no editable control', async () => {
    renderRaw()

    await screen.findByText(/port = 9999/)
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  })

  it('copies the text to the clipboard', async () => {
    // userEvent.setup() installs a working clipboard stub. Do not stub
    // navigator by spreading it: its properties live on the prototype, so
    // {...navigator} is very nearly empty.
    const user = userEvent.setup()
    renderRaw()

    await screen.findByText(/port = 9999/)
    await user.click(screen.getByRole('button', { name: 'Copy' }))

    await waitFor(async () => expect(await navigator.clipboard.readText()).toBe(TOML))
    expect(await screen.findByRole('button', { name: 'Copied' })).toBeInTheDocument()
  })

  it('reports a preview failure rather than rendering an empty file', async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 400,
      json: async () => ({ detail: 'config.toml is not valid TOML' }),
    } as Response)

    renderRaw()

    expect(await screen.findByRole('alert')).toHaveTextContent('config.toml is not valid TOML')
  })
})
