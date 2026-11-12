import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ScopeTabs } from './ScopeTabs'

const LABELS = {
  button: 'override for a project',
  search: 'search projects',
  noMatch: 'no project matches',
  hint: 'opens the project',
}

function renderTabs(overrides: Partial<Parameters<typeof ScopeTabs>[0]> = {}) {
  const onSelect = vi.fn()
  render(
    <ScopeTabs
      projects={['Alpha', 'Release 2.0']}
      selected={null}
      addable={['Beta', 'Gamma']}
      onSelect={onSelect}
      globalLabel="Global"
      addLabels={LABELS}
      {...overrides}
    />,
  )
  return { onSelect }
}

async function openPicker(user = userEvent.setup()) {
  await user.click(screen.getByRole('button', { name: LABELS.button }))
  return { user, picker: screen.getByRole('dialog', { name: LABELS.button }) }
}

test('the global tab is selected when no project is', () => {
  renderTabs()
  expect(screen.getByRole('tab', { name: 'Global' })).toHaveAttribute('aria-selected', 'true')
  expect(screen.getByRole('tab', { name: 'Alpha' })).toHaveAttribute('aria-selected', 'false')
})

test('a project tab is selected when it is the current scope', () => {
  renderTabs({ selected: 'Release 2.0' })
  expect(screen.getByRole('tab', { name: 'Release 2.0' })).toHaveAttribute('aria-selected', 'true')
  expect(screen.getByRole('tab', { name: 'Global' })).toHaveAttribute('aria-selected', 'false')
})

test('choosing the global tab reports null, not a name', async () => {
  const { onSelect } = renderTabs({ selected: 'Alpha' })
  await userEvent.click(screen.getByRole('tab', { name: 'Global' }))
  expect(onSelect).toHaveBeenCalledWith(null)
})

test('choosing a project tab reports its name', async () => {
  const { onSelect } = renderTabs()
  await userEvent.click(screen.getByRole('tab', { name: 'Alpha' }))
  expect(onSelect).toHaveBeenCalledWith('Alpha')
})

test('the plus button is not a form field and starts closed', () => {
  renderTabs()
  const button = screen.getByRole('button', { name: LABELS.button })
  expect(button).toHaveTextContent('+')
  expect(button).toHaveAttribute('aria-expanded', 'false')
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
})

test('the picker offers only projects without a tab', async () => {
  renderTabs()
  const { picker } = await openPicker()
  expect(within(picker).getByRole('button', { name: 'Beta' })).toBeInTheDocument()
  expect(within(picker).getByRole('button', { name: 'Gamma' })).toBeInTheDocument()
  expect(within(picker).queryByRole('button', { name: 'Alpha' })).not.toBeInTheDocument()
  expect(picker).toHaveTextContent(LABELS.hint)
})

test('picking a project selects it and closes the picker', async () => {
  const { onSelect } = renderTabs()
  const { user, picker } = await openPicker()
  await user.click(within(picker).getByRole('button', { name: 'Gamma' }))
  expect(onSelect).toHaveBeenCalledWith('Gamma')
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
})

test('typing filters the list and Enter picks the first match', async () => {
  const { onSelect } = renderTabs()
  const { user, picker } = await openPicker()
  const search = within(picker).getByRole('searchbox', { name: LABELS.search })
  expect(search).toHaveFocus()
  await user.type(search, 'gam')
  expect(within(picker).queryByRole('button', { name: 'Beta' })).not.toBeInTheDocument()
  await user.keyboard('{Enter}')
  expect(onSelect).toHaveBeenCalledWith('Gamma')
})

test('a search without a match says so', async () => {
  renderTabs()
  const { user, picker } = await openPicker()
  await user.type(within(picker).getByRole('searchbox'), 'zzz')
  expect(picker).toHaveTextContent(LABELS.noMatch)
})

test('Escape closes the picker and returns focus to the plus button', async () => {
  const { onSelect } = renderTabs()
  const { user } = await openPicker()
  await user.keyboard('{Escape}')
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: LABELS.button })).toHaveFocus()
  expect(onSelect).not.toHaveBeenCalled()
})

test('a click outside closes the picker', async () => {
  renderTabs()
  const { user } = await openPicker()
  await user.click(document.body)
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
})

test('the plus button is absent when every known project already has a tab', () => {
  renderTabs({ addable: [] })
  expect(screen.queryByRole('button', { name: LABELS.button })).not.toBeInTheDocument()
})
