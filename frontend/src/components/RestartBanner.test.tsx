import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { RestartBanner, type RestartOffer } from './RestartBanner'
import { i18n } from '../i18n'

// The assertions match the English copy.
beforeEach(() => i18n.changeLanguage('en'))

const fetchMock = vi.fn()

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
})
afterEach(() => vi.unstubAllGlobals())

function jsonResponse(body: unknown, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as Response
}

const OFFER: RestartOffer = { startedAt: '2026-11-18T08:00:00Z', inFlight: 0 }

function renderBanner(fields: string[], restart?: RestartOffer) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <RestartBanner fields={fields} restart={restart} />
    </QueryClientProvider>,
  )
}

function here() {
  return { host: window.location.hostname, port: Number(window.location.port || 80), tls: false }
}

describe('RestartBanner', () => {
  it('renders nothing when nothing needs a restart', () => {
    renderBanner([])

    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('says a restart is needed and names the fields', () => {
    renderBanner(['host', 'port'])

    expect(screen.getByRole('status')).toHaveTextContent(
      'Some changes need a service restart to take effect.',
    )
    expect(screen.getByRole('status')).toHaveTextContent('host, port')
  })

  it('offers no restart when the service cannot restart itself or the viewer may not', () => {
    renderBanner(['port'])

    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('warns about runs in flight before restarting', async () => {
    renderBanner(['port'], { ...OFFER, inFlight: 2 })

    await userEvent.click(screen.getByRole('button', { name: 'Restart now' }))

    expect(screen.getByText(/2 agent runs are still in flight/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('restarts and waits for the new run of the service', async () => {
    fetchMock.mockImplementation(async (url: string) => {
      if (url.endsWith('/restart')) return jsonResponse({ ...here(), in_flight_tasks: 0 }, 202)
      return jsonResponse({ service: { started_at: '2026-11-18T09:00:00Z' } })
    })
    renderBanner(['port'], OFFER)

    await userEvent.click(screen.getByRole('button', { name: 'Restart now' }))
    await userEvent.click(screen.getByRole('button', { name: 'Restart now' }))

    expect(await screen.findByText('Restarting the service…')).toBeInTheDocument()
    await waitFor(
      () => expect(screen.getByRole('status')).toHaveTextContent('Service restarted.'),
      {
        timeout: 3000,
      },
    )
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/admin/api/restart')
    expect(init.method).toBe('POST')
  })

  it('links to the new address when the service moves', async () => {
    fetchMock.mockImplementation(async (url: string) => {
      if (url.endsWith('/restart')) return jsonResponse({ ...here(), port: 9999 }, 202)
      throw new TypeError('Failed to fetch')
    })
    renderBanner(['port'], OFFER)

    await userEvent.click(screen.getByRole('button', { name: 'Restart now' }))
    await userEvent.click(screen.getByRole('button', { name: 'Restart now' }))

    const link = await screen.findByRole('link')
    expect(link.getAttribute('href')).toContain(':9999/admin/')
  })

  it('shows why the service refused to restart', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        {
          detail: {
            message: 'The configuration on disk is not valid.',
            issues: [{ path: 'port', message: 'port: not a number' }],
          },
        },
        422,
      ),
    )
    renderBanner(['port'], OFFER)

    await userEvent.click(screen.getByRole('button', { name: 'Restart now' }))
    await userEvent.click(screen.getByRole('button', { name: 'Restart now' }))

    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('port: not a number'))
  })
})
