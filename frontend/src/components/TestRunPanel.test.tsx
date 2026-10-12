import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ComponentProps } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, expect, test, vi } from 'vitest'
import { TestRunPanel } from './TestRunPanel'
import { i18n } from '../i18n'
import { chooseOption, dropdownValue, openDropdown } from '../test/prime'

// The assertions match the English copy.
beforeEach(() => i18n.changeLanguage('en'))

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
        {...props}
      />
    </MemoryRouter>,
  )
}

test('lists catalogue models with their routing family', async () => {
  renderPanel()
  const list = await openDropdown(userEvent.setup(), 'Model')
  expect(within(list).getByRole('option', { name: /claude-opus-5/, hidden: true })).toBeInTheDocument()
})

test('marks a fallback model so a degraded call is visible', async () => {
  renderPanel()
  const list = await openDropdown(userEvent.setup(), 'Model')
  const option = within(list).getByRole('option', { name: /my-model/, hidden: true })
  expect(option.textContent).toMatch(/fallback/i)
})

/** Opens the free-text model field via the picker's "Other model…" entry. */
async function typeCustomModel(user: ReturnType<typeof userEvent.setup>, text: string) {
  await chooseOption(user, 'Model', 'Other model…')
  const field = screen.getByLabelText('Model ID')
  await user.clear(field)
  if (text) await user.type(field, text)
  return field
}

test('a free-text model reaches the request', async () => {
  renderPanel()
  const user = userEvent.setup()

  await typeCustomModel(user, 'typed-model')
  await user.click(screen.getByRole('button', { name: /test run/i }))

  await waitFor(() =>
    expect(mutate).toHaveBeenCalledWith(expect.objectContaining({ model: 'typed-model' })),
  )
})

test('the free-text field stays hidden until "Other model…" is picked', async () => {
  renderPanel()
  expect(screen.queryByLabelText('Model ID')).not.toBeInTheDocument()

  await chooseOption(userEvent.setup(), 'Model', 'Other model…')
  expect(screen.getByLabelText('Model ID')).toBeInTheDocument()
})

test('without a catalogue the free-text field is the model control', () => {
  modelsState = { isLoading: false, isError: true, data: undefined }
  renderPanel()
  const field = screen.getByLabelText('Model')
  expect(field.tagName).toBe('INPUT')
})

test('the picker shows the catalogue model it selected', async () => {
  renderPanel()
  const user = userEvent.setup()

  await chooseOption(user, 'Model', /claude-opus-5/)

  expect(dropdownValue('Model')).toBe('claude-opus-5 · adaptive')
  expect(screen.queryByLabelText('Model ID')).not.toBeInTheDocument()
})

test('the picker reads "Other model…" for a model the catalogue lacks', async () => {
  renderPanel()
  const user = userEvent.setup()

  await typeCustomModel(user, 'typed-model')

  expect(dropdownValue('Model')).toBe('Other model…')
})

test('a picked fallback model says so beside the picker', async () => {
  renderPanel()
  await chooseOption(userEvent.setup(), 'Model', /my-model/)
  expect(screen.getByText(/no tuned routing/i)).toBeInTheDocument()
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

test('shows the token usage, reasoning included in the output', async () => {
  runState = {
    isPending: false,
    error: null,
    data: {
      text: 'the answer',
      latency_ms: 42,
      usage: { input_tokens: 812, output_tokens: 356, reasoning_tokens: 120 },
      resolved: { provider: 'openai', model: 'o3', credential_scope: 'global' },
    },
  }
  renderPanel()

  expect(await screen.findByText(/812 input tokens \/ 356 output tokens/)).toBeInTheDocument()
  expect(screen.getByText(/incl\. 120 reasoning/)).toBeInTheDocument()
})

test('shows no token chip when the provider reported no usage', async () => {
  runState = {
    isPending: false,
    error: null,
    data: {
      text: 'the answer',
      latency_ms: 42,
      usage: null,
      resolved: { provider: 'anthropic', model: 'claude-opus-5', credential_scope: 'global' },
    },
  }
  renderPanel()

  expect(await screen.findByText(/the answer/)).toBeInTheDocument()
  expect(screen.queryByText('Tokens')).not.toBeInTheDocument()
})

test('the button is disabled while a run is in flight', async () => {
  runState = { isPending: true, data: undefined, error: null }
  renderPanel()
  // A model is picked first, so this asserts the in-flight gate specifically
  // rather than passing because the (empty) model gate happens to fire.
  await chooseOption(userEvent.setup(), 'Model', /claude-opus-5/)
  expect(screen.getByRole('button', { name: /test run/i })).toBeDisabled()
})

test('a non-admin cannot start a run', async () => {
  renderPanel({ isAdmin: false })
  await chooseOption(userEvent.setup(), 'Model', /claude-opus-5/)
  expect(screen.getByRole('button', { name: /test run/i })).toBeDisabled()
})

test('the button is disabled until a model is given', async () => {
  // An empty model would reach a real client and cost a guaranteed 502 on a
  // paid endpoint. Whitespace is not a model name either.
  renderPanel()
  const button = screen.getByRole('button', { name: /test run/i })
  expect(button).toBeDisabled()

  const user = userEvent.setup()
  const field = await typeCustomModel(user, '   ')
  expect(button).toBeDisabled()

  await user.clear(field)
  await user.type(field, 'claude-opus-5')
  expect(button).toBeEnabled()
})

test('the in-flight notice is announced', () => {
  runState = { isPending: true, data: undefined, error: null }
  renderPanel()
  expect(screen.getByText(/running/i)).toHaveAttribute('aria-live', 'polite')
})

test('the admin-gate notice is announced', () => {
  renderPanel({ isAdmin: false })
  expect(screen.getByText(/administrator/i)).toHaveAttribute('aria-live', 'polite')
})

test('has no add-model control — that lives on the LLM view', async () => {
  renderPanel()
  const list = await openDropdown(userEvent.setup(), 'Model')
  await within(list).findByRole('option', { name: /claude-opus-5/, hidden: true })
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
