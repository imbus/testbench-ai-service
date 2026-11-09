import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { DraftProvider, useDraft } from '../state/draft'
import { PendingBanner } from './PendingBanner'
import { i18n } from '../i18n'

// The assertions match the English copy.
beforeEach(() => i18n.changeLanguage('en'))

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

function renderBanner(
  saved: Record<string, unknown> = { port: 8010, host: '127.0.0.1' },
  edits: Record<string, unknown> = { port: 9999 },
) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <DraftProvider saved={saved}>
          <Seed edits={edits} />
          <PendingBanner />
        </DraftProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const DIFF_RESPONSE = {
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
} as Response

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

  it('counts the changes per section, each linking to its screen', async () => {
    renderBanner(
      { port: 8010 },
      {
        port: 9999,
        host: '0.0.0.0',
        'llm_config.default_model': 'gpt-x',
        'agents.reviewer.enabled': false,
        'projects.Demo.language': 'en',
        'logging.console.log_level': 'DEBUG',
      },
    )

    await userEvent.click(screen.getByText('seed'))
    const strip = within(screen.getByRole('status'))

    expect(strip.getByRole('link', { name: 'Service 2' })).toHaveAttribute('href', '/admin/service')
    expect(strip.getByRole('link', { name: 'LLM provider 1' })).toHaveAttribute('href', '/admin/llm')
    expect(strip.getByRole('link', { name: 'Agents 1' })).toHaveAttribute('href', '/admin/agents')
    expect(strip.getByRole('link', { name: 'Projects 1' })).toHaveAttribute('href', '/admin/projects')
    expect(strip.getByRole('link', { name: 'Logging 1' })).toHaveAttribute('href', '/admin/logging')
    // The raw dotted paths are the diff dialog's job, not the strip's.
    expect(screen.getByRole('status')).not.toHaveTextContent('llm_config.default_model')
  })

  it('opens the diff dialog from its single primary button', async () => {
    fetchMock.mockResolvedValue(DIFF_RESPONSE)
    renderBanner()

    await userEvent.click(screen.getByText('seed'))
    const strip = within(screen.getByRole('status'))
    expect(strip.queryByRole('button', { name: 'View diff' })).not.toBeInTheDocument()
    expect(strip.queryByRole('button', { name: 'Apply' })).not.toBeInTheDocument()
    await userEvent.click(strip.getByRole('button', { name: 'Review & apply…' }))

    expect(await screen.findByRole('dialog')).toBeInTheDocument()
    // Opening it writes nothing: applying happens behind the diff's approval.
    expect(
      fetchMock.mock.calls.filter(([url]) => String(url).includes('/config/apply')),
    ).toHaveLength(0)
  })

  it('asks before discarding, and keeps the changes on cancel', async () => {
    renderBanner()

    await userEvent.click(screen.getByText('seed'))
    await userEvent.click(screen.getByRole('button', { name: 'Discard…' }))

    expect(screen.getByRole('status')).toHaveTextContent('Discard 1 unapplied change?')
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(screen.getByRole('status')).toHaveTextContent('1 unapplied changes')
    expect(screen.getByRole('button', { name: 'Discard…' })).toBeInTheDocument()
  })

  it('discards every change once confirmed', async () => {
    renderBanner()

    await userEvent.click(screen.getByText('seed'))
    await userEvent.click(screen.getByRole('button', { name: 'Discard…' }))
    await userEvent.click(screen.getByRole('button', { name: 'Discard' }))

    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })
})
