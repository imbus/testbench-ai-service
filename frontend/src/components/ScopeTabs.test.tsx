import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ScopeTabs } from './ScopeTabs'

function renderTabs(overrides: Partial<Parameters<typeof ScopeTabs>[0]> = {}) {
  const onSelect = vi.fn()
  render(
    <ScopeTabs
      projects={['Alpha', 'Release 2.0']}
      selected={null}
      addable={['Beta']}
      onSelect={onSelect}
      globalLabel="Global"
      addLabel="add project"
      {...overrides}
    />,
  )
  return { onSelect }
}

test('the global tab is selected when no project is', () => {
  renderTabs()
  expect(screen.getByRole('tab', { name: 'Global' })).toHaveAttribute('aria-selected', 'true')
  expect(screen.getByRole('tab', { name: 'Alpha' })).toHaveAttribute('aria-selected', 'false')
})

test('a project tab is selected when it is the current scope', () => {
  renderTabs({ selected: 'Release 2.0' })
  expect(screen.getByRole('tab', { name: 'Release 2.0' })).toHaveAttribute(
    'aria-selected',
    'true',
  )
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

test('the add select offers only projects without a tab', () => {
  renderTabs()
  const select = screen.getByRole('combobox', { name: 'add project' })
  expect(select).toHaveTextContent('Beta')
  expect(select).not.toHaveTextContent('Alpha')
})

test('picking from the add select selects that project', async () => {
  const { onSelect } = renderTabs()
  await userEvent.selectOptions(screen.getByRole('combobox', { name: 'add project' }), 'Beta')
  expect(onSelect).toHaveBeenCalledWith('Beta')
})

test('the add select is absent when every known project already has a tab', () => {
  renderTabs({ addable: [] })
  expect(screen.queryByRole('combobox', { name: 'add project' })).not.toBeInTheDocument()
})
