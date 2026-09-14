import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ComponentProps } from 'react'
import { beforeEach, expect, test, vi } from 'vitest'
import { joinPath, splitPath } from '../api/paths'
import { ModelTable } from './ModelTable'

const setValue = vi.fn()
const unsetSubtree = vi.fn()
let edits: Record<string, unknown> = {}

vi.mock('../state/draft', () => ({
  useDraft: () => ({
    edits,
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
  edits = {}
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


test('a dotted model name produces one key, not a nested table', async () => {
  // OpenAI's own set is full of dotted names (gpt-4.1, gpt-5.1, gpt-5.5), so
  // this is the primary case for this table, not an edge one. Concatenating
  // `llm_config.extra_models.` + `gpt-5.5` yields a path that tokenizes into
  // FIVE segments and addresses a nested table nobody asked for.
  renderTable()
  const user = userEvent.setup()

  await user.type(screen.getByLabelText(/new model/i), 'gpt-5.5')
  await user.selectOptions(screen.getByLabelText(/new provider/i), 'openai')
  await user.selectOptions(screen.getByLabelText(/new routing/i), 'chat')
  await user.click(screen.getByRole('button', { name: /add/i }))

  const expected = joinPath(['llm_config', 'extra_models', 'gpt-5.5', 'provider'])
  expect(expected).toBe('llm_config.extra_models."gpt-5.5".provider')
  expect(setValue).toHaveBeenCalledWith(expected, 'openai')
  expect(setValue).toHaveBeenCalledWith(
    joinPath(['llm_config', 'extra_models', 'gpt-5.5', 'routing']),
    'chat',
  )

  // One key, four segments, the name intact -- the property, not the spelling.
  expect(splitPath(expected)).toEqual(['llm_config', 'extra_models', 'gpt-5.5', 'provider'])
  expect(splitPath('llm_config.extra_models.gpt-5.5.provider')).toHaveLength(5)
})

test('removing a dotted model quotes the name too', async () => {
  renderTable({ entries: { 'gpt-5.5': { provider: 'openai', routing: 'chat' } } })
  const user = userEvent.setup()

  await user.click(screen.getByRole('button', { name: /remove/i }))

  expect(unsetSubtree).toHaveBeenCalledWith('llm_config.extra_models."gpt-5.5"')
})

test('the columns are labelled', () => {
  renderTable()
  expect(screen.getByText('Model')).toBeInTheDocument()
  expect(screen.getByText('Provider')).toBeInTheDocument()
  expect(screen.getByText('Request shape')).toBeInTheDocument()
})

test('a queued addition is listed immediately', () => {
  // Consistent with Field.tsx's `draft.valueOf(key, saved)` on this same
  // screen: the table shows what will be written, not what is on disk.
  edits = {
    'llm_config.extra_models."gpt-5.5".provider': 'openai',
    'llm_config.extra_models."gpt-5.5".routing': 'reasoning',
  }
  renderTable({ entries: {} })

  // Scoped to the row: 'openai' and 'reasoning' are also option labels in the
  // add row below, so a bare getByText would not prove the row exists.
  const row = screen.getByText('gpt-5.5').closest('div')
  expect(row).toHaveTextContent('openai')
  expect(row).toHaveTextContent('reasoning')
  expect(screen.queryByText(/no additional models/i)).not.toBeInTheDocument()
})

test('a queued removal drops the row immediately', () => {
  edits = { 'llm_config.extra_models.claude-opus-6': null }
  renderTable()

  expect(screen.queryByText('claude-opus-6')).not.toBeInTheDocument()
  expect(screen.getByText(/no additional models/i)).toBeInTheDocument()
})

test('an edit outside this table is ignored', () => {
  edits = { 'llm_config.timeout': 42, 'projects."a.b".language': 'en' }
  renderTable()

  expect(screen.getByText('claude-opus-6')).toBeInTheDocument()
  expect(screen.queryByText('42')).not.toBeInTheDocument()
})
