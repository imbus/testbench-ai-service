import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ComponentProps } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, expect, test, vi } from 'vitest'
import { TestRunPanel } from './TestRunPanel'

const mutate = vi.fn()
let runState: Record<string, unknown> = {}
let modelsState: Record<string, unknown> = {}

vi.mock('../api/queries', () => ({
  useModels: () => modelsState,
  useProjects: () => ({ data: { projects: [] }, isLoading: false, isError: false }),
}))

vi.mock('../api/mutations', () => ({
  useTestPrompt: () => ({ mutate, ...runState }),
}))

beforeEach(() => {
  mutate.mockReset()
  runState = { isPending: false, data: undefined, error: null }
  modelsState = {
    isLoading: false,
    isError: false,
    data: {
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
    },
  }
})

function renderPanel(props: Partial<ComponentProps<typeof TestRunPanel>> = {}) {
  return render(
    <MemoryRouter>
      <TestRunPanel
        messages={[
          { role: 'user', source: 'inline', file: null, content: 'hi', readable: true },
        ]}
        vars={{}}
        agentContext={{}}
        isAdmin
        lang="en"
        {...props}
      />
    </MemoryRouter>,
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
  renderPanel()
  const user = userEvent.setup()

  const field = screen.getByLabelText(/model/i)
  await user.clear(field)
  await user.type(field, 'typed-model')
  await user.click(screen.getByRole('button', { name: /test run/i }))

  await waitFor(() =>
    expect(mutate).toHaveBeenCalledWith(expect.objectContaining({ model: 'typed-model' })),
  )
})

test('shows the resolved route including the credential scope', async () => {
  runState = {
    isPending: false,
    error: null,
    data: {
      text: 'the answer',
      latency_ms: 42,
      resolved: {
        provider: 'anthropic',
        model: 'claude-opus-5',
        credential_scope: 'global',
      },
    },
  }
  renderPanel()

  expect(await screen.findByText(/the answer/)).toBeInTheDocument()
  expect(screen.getByText(/42/)).toBeInTheDocument()
  expect(screen.getByText(/global key/i)).toBeInTheDocument()
})

test('the button is disabled while a run is in flight', () => {
  runState = { isPending: true, data: undefined, error: null }
  renderPanel()
  expect(screen.getByRole('button', { name: /test run/i })).toBeDisabled()
})

test('a non-admin cannot start a run', () => {
  renderPanel({ isAdmin: false })
  expect(screen.getByRole('button', { name: /test run/i })).toBeDisabled()
})

test('has no add-model control — that lives on the LLM view', async () => {
  renderPanel()
  await screen.findByRole('option', { name: /claude-opus-5/ })
  expect(screen.queryByRole('button', { name: /add model/i })).not.toBeInTheDocument()
})

test('the hint to add a model is an in-app link, not a full page load', async () => {
  // A plain <a href> would bypass PromptEditor's useBlocker and fire
  // beforeunload, losing the operator's unsaved draft. react-router's Link
  // keeps the guard in charge.
  renderPanel()
  const link = await screen.findByRole('link', { name: /llm/i })
  expect(link).toHaveAttribute('href', '/admin/llm')
})
