import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { DraftProvider, useDraft } from '../state/draft'
import { PendingBanner } from './PendingBanner'

const fetchMock = vi.fn()

function Seed({ edits }: { edits: Record<string, unknown> }) {
  const draft = useDraft()
  return (
    <button
      onClick={() => {
        for (const [path, value] of Object.entries(edits)) draft.setValue(path, value)
      }}
    >
      seed
    </button>
  )
}

function renderBanner(saved: Record<string, unknown> = { port: 8010, host: '127.0.0.1' }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <DraftProvider saved={saved}>
        <Seed edits={{ port: 9999 }} />
        <PendingBanner lang="en" />
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

describe('PendingBanner', () => {
  it('renders nothing when there are no changes', () => {
    renderBanner()

    expect(screen.queryByText(/unapplied changes/)).not.toBeInTheDocument()
  })

  it('counts the pending changes once there are some', async () => {
    renderBanner()

    await userEvent.click(screen.getByText('seed'))

    expect(screen.getByRole('status')).toHaveTextContent('1 unapplied changes')
  })

  it('lists the changed paths', async () => {
    renderBanner()

    await userEvent.click(screen.getByText('seed'))

    expect(screen.getByRole('status')).toHaveTextContent('port')
  })

  it('discards every change', async () => {
    renderBanner()

    await userEvent.click(screen.getByText('seed'))
    await userEvent.click(screen.getByRole('button', { name: 'Discard' }))

    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('opens the diff dialog', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        valid: true,
        issues: [],
        diffs: [{ path: '/tmp/config.toml', diff: '-port = 8010\n+port = 9999\n', added: 1, removed: 1 }],
        restart_required: ['port'],
        in_flight_tasks: 0,
        toml: '',
      }),
    } as Response)
    renderBanner()

    await userEvent.click(screen.getByText('seed'))
    await userEvent.click(screen.getByRole('button', { name: 'View diff' }))

    expect(await screen.findByRole('dialog')).toBeInTheDocument()
  })
})
