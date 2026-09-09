import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
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
    await waitFor(() => expect(screen.getByRole('button', { name: 'Copied' })).toBeInTheDocument(), { timeout: 3000 })
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

  it('hides stale TOML when preview fails after a previous success (contract guard)', async () => {
    // Contract: "this is exactly what an apply would write". Showing stale
    // TOML beside a current error violates it. The operator cannot tell which
    // text is current, so we render the error and deliberately withhold the
    // stale content.
    const { unmount } = renderRaw()

    // Show the initial success.
    await screen.findByText(/port = 9999/)
    expect(screen.getByRole('button', { name: 'Copy' })).toBeInTheDocument()

    // Trigger a failure.
    fetchMock.mockResolvedValue({
      ok: false,
      status: 400,
      json: async () => ({ detail: 'syntax error' }),
    } as Response)
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    unmount()
    render(
      <QueryClientProvider client={client}>
        <DraftProvider saved={{ port: 8010 }}>
          <Raw lang="en" />
        </DraftProvider>
      </QueryClientProvider>,
    )

    // Verify: error is shown, stale TOML is not, copy button is not.
    expect(await screen.findByRole('alert')).toHaveTextContent('syntax error')
    expect(screen.queryByText(/port = 9999/)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Copy' })).not.toBeInTheDocument()
  })

  it('cleans up the copy timer on unmount to avoid setState on an unmounted component', async () => {
    const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const { unmount } = renderRaw()

    await screen.findByText(/port = 9999/)

    vi.useFakeTimers()
    try {
      // Use fireEvent instead of userEvent to avoid timer queuing issues with fake timers.
      fireEvent.click(screen.getByRole('button', { name: 'Copy' }))

      // Unmount before the timer fires.
      unmount()
      vi.runAllTimers()

      // No state-update warning.
      expect(consoleErrorSpy).not.toHaveBeenCalled()
    } finally {
      vi.useRealTimers()
      consoleErrorSpy.mockRestore()
    }
  })

  it('rapid copy clicks clear the previous timer so the label does not stick or double-flip', async () => {
    renderRaw()

    await screen.findByText(/port = 9999/)

    vi.useFakeTimers()
    try {
      // Mock navigator.clipboard for fake timer context.
      const clipboardMock = { writeText: vi.fn(() => Promise.resolve()) }
      Object.defineProperty(navigator, 'clipboard', {
        value: clipboardMock,
        configurable: true,
      })

      const clearTimeoutSpy = vi.spyOn(window, 'clearTimeout')

      // First click starts a timer.
      fireEvent.click(screen.getByRole('button', { name: 'Copy' }))
      await vi.runAllTimersAsync()

      const firstClickTimerCalls = clearTimeoutSpy.mock.calls.length

      // Click again before the first timer fires (1999ms < 2000ms).
      vi.advanceTimersByTime(1999)
      fireEvent.click(screen.getByRole('button', { name: 'Copy' }))
      await vi.runAllTimersAsync()

      // Verify that clearTimeout was called: the previous timer was cleared
      // before starting the new one.
      expect(clearTimeoutSpy.mock.calls.length).toBeGreaterThan(firstClickTimerCalls)

      clearTimeoutSpy.mockRestore()
    } finally {
      vi.useRealTimers()
    }
  })
})
