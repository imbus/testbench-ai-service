import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ComponentProps } from 'react'
import { beforeEach, expect, test, vi } from 'vitest'
import { ModelTable } from './ModelTable'

const setValue = vi.fn()
const unsetSubtree = vi.fn()

vi.mock('../state/draft', () => ({
  useDraft: () => ({
    edits: {},
    changeCount: 0,
    isChanged: () => false,
    valueOf: (_path: string, fallback: unknown) => fallback,
    setValue,
    unsetValue: vi.fn(),
    unsetSubtree,
    revert: vi.fn(),
    discardAll: vi.fn(),
  }),
}))

beforeEach(() => {
  setValue.mockReset()
  unsetSubtree.mockReset()
})

function renderTable(props: Partial<ComponentProps<typeof ModelTable>> = {}) {
  return render(
    <ModelTable
      entries={{ 'claude-opus-6': { provider: 'anthropic', routing: 'adaptive' } }}
      issues={[]}
      lang="en"
      {...props}
    />,
  )
}

test('lists the configured models', () => {
  renderTable()
  expect(screen.getByText('claude-opus-6')).toBeInTheDocument()
})

test('does not list built-in models', () => {
  // Built-ins are not editable here; showing them would imply otherwise.
  renderTable()
  expect(screen.queryByText('gpt-4o')).not.toBeInTheDocument()
})

test('adding a model writes both draft edits', async () => {
  renderTable()
  const user = userEvent.setup()

  await user.type(screen.getByLabelText(/new model/i), 'gpt-6')
  await user.selectOptions(screen.getByLabelText(/new provider/i), 'openai')
  await user.selectOptions(screen.getByLabelText(/new routing/i), 'reasoning')
  await user.click(screen.getByRole('button', { name: /add/i }))

  expect(setValue).toHaveBeenCalledWith('llm_config.extra_models.gpt-6.provider', 'openai')
  expect(setValue).toHaveBeenCalledWith('llm_config.extra_models.gpt-6.routing', 'reasoning')
})

test('removing a model drops the whole entry', async () => {
  renderTable()
  const user = userEvent.setup()

  await user.click(screen.getByRole('button', { name: /remove/i }))

  expect(unsetSubtree).toHaveBeenCalledWith('llm_config.extra_models.claude-opus-6')
})

test('routing choices are filtered to what the provider accepts', async () => {
  renderTable()
  const user = userEvent.setup()

  await user.selectOptions(screen.getByLabelText(/new provider/i), 'anthropic')

  const routing = screen.getByLabelText(/new routing/i)
  expect(within(routing).queryByRole('option', { name: 'chat' })).not.toBeInTheDocument()
  expect(within(routing).getByRole('option', { name: 'adaptive' })).toBeInTheDocument()
})

test('a custom-provider entry can only be fallback', async () => {
  renderTable()
  const user = userEvent.setup()

  await user.selectOptions(screen.getByLabelText(/new provider/i), 'custom')

  const routing = screen.getByLabelText(/new routing/i)
  expect(within(routing).getByRole('option', { name: 'fallback' })).toBeInTheDocument()
  expect(within(routing).queryByRole('option', { name: 'adaptive' })).not.toBeInTheDocument()
})

test('renders a config issue against the offending row', () => {
  renderTable({
    issues: [
      {
        path: 'llm_config.extra_models.claude-opus-6.routing',
        message: 'routing is not available for provider',
        toml_section: '[testbench-ai-service.llm_config]',
      },
    ],
  })
  expect(screen.getByRole('alert')).toHaveTextContent(/not available/)
})

test('an issue on a different row does not mark this one', () => {
  renderTable({
    issues: [
      {
        path: 'llm_config.extra_models.something-else.routing',
        message: 'bad',
        toml_section: '[testbench-ai-service.llm_config]',
      },
    ],
  })
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})

test('a read-only operator cannot add or remove', () => {
  renderTable({ readOnly: true })
  expect(screen.getByRole('button', { name: /add/i })).toBeDisabled()
  expect(screen.getByRole('button', { name: /remove/i })).toBeDisabled()
})
