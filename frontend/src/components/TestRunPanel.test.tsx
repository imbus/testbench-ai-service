import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ComponentProps } from 'react'
import { expect, test, vi } from 'vitest'
import { TestRunPanel } from './TestRunPanel'

vi.mock('../api/models', () => ({
  fetchModels: vi.fn().mockResolvedValue({
    providers: [
      {
        provider: 'anthropic',
        key_present: true,
        models: [
          { id: 'claude-opus-5', routing: 'adaptive', source: 'builtin' },
          { id: 'my-model', routing: 'fallback', source: 'config' },
        ],
      },
    ],
  }),
}))

const testPrompt = vi.fn()
vi.mock('../api/prompts', async (importOriginal) => ({
  ...(await importOriginal<object>()),
  testPrompt: (...args: unknown[]) => testPrompt(...args),
}))

function renderPanel(props: Partial<ComponentProps<typeof TestRunPanel>> = {}) {
  return render(
    <TestRunPanel
      messages={[{ role: 'user', source: 'inline', file: null, content: 'hi', readable: true }]}
      vars={{}}
      agentContext={{}}
      isAdmin
      lang="en"
      {...props}
    />,
  )
}

test('lists catalogue models with their routing family', async () => {
  renderPanel()
  expect(await screen.findByRole('option', { name: /claude-opus-5/ })).toBeInTheDocument()
})

test('marks a fallback model so a degraded call is visible', async () => {
  renderPanel()
  const option = await screen.findByRole('option', { name: /my-model/ })
  expect(option.textContent).toMatch(/fallback/i)
})

test('a free-text model reaches the request', async () => {
  testPrompt.mockResolvedValue({
    text: 'ok',
    latency_ms: 12,
    resolved: { provider: 'anthropic', model: 'typed-model', credential_scope: 'global' },
  })
  renderPanel()
  const user = userEvent.setup()

  await user.clear(screen.getByLabelText(/model/i))
  await user.type(screen.getByLabelText(/model/i), 'typed-model')
  await user.click(screen.getByRole('button', { name: /test run/i }))

  await waitFor(() =>
    expect(testPrompt).toHaveBeenCalledWith(expect.objectContaining({ model: 'typed-model' })),
  )
})

test('shows the resolved route including the credential scope', async () => {
  testPrompt.mockResolvedValue({
    text: 'the answer',
    latency_ms: 42,
    resolved: { provider: 'anthropic', model: 'claude-opus-5', credential_scope: 'global' },
  })
  renderPanel()
  const user = userEvent.setup()

  await user.click(screen.getByRole('button', { name: /test run/i }))

  expect(await screen.findByText(/the answer/)).toBeInTheDocument()
  expect(screen.getByText(/42/)).toBeInTheDocument()
  expect(screen.getByText(/global/i)).toBeInTheDocument()
})

test('the button is disabled while a run is in flight', async () => {
  let resolve: (value: unknown) => void = () => {}
  testPrompt.mockReturnValue(new Promise((r) => (resolve = r)))
  renderPanel()
  const user = userEvent.setup()

  const button = screen.getByRole('button', { name: /test run/i })
  await user.click(button)
  expect(button).toBeDisabled()

  resolve({
    text: 'x',
    latency_ms: 1,
    resolved: { provider: 'anthropic', model: 'm', credential_scope: 'global' },
  })
  await waitFor(() => expect(button).not.toBeDisabled())
})

test('a non-admin cannot start a run', async () => {
  renderPanel({ isAdmin: false })
  expect(screen.getByRole('button', { name: /test run/i })).toBeDisabled()
})

test('has no add-model control — that lives on the LLM view', async () => {
  renderPanel()
  await screen.findByRole('option', { name: /claude-opus-5/ })
  expect(screen.queryByRole('button', { name: /add model/i })).not.toBeInTheDocument()
})
