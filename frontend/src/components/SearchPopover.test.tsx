import { useRef, useState } from 'react'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { SearchPopover } from './SearchPopover'

function Picker({ onPick }: { onPick: (name: string) => void }) {
  const anchor = useRef<HTMLDivElement>(null)
  const [query, setQuery] = useState('')
  const names = ['Alpha', 'Beta', 'Gamma'].filter((name) =>
    name.toLowerCase().includes(query.toLowerCase()),
  )
  return (
    <div ref={anchor}>
      <SearchPopover
        anchor={anchor}
        label="Pick"
        searchLabel="Search"
        query={query}
        onQuery={setQuery}
        onEnter={() => names[0] && onPick(names[0])}
        onEscape={() => {}}
        onDismiss={() => {}}
      >
        {names.map((name) => (
          <li key={name}>
            <button type="button" onClick={() => onPick(name)}>
              {name}
            </button>
          </li>
        ))}
      </SearchPopover>
    </div>
  )
}

it('walks the entries with the arrow keys and picks the focused one on Enter', async () => {
  const onPick = vi.fn()
  render(<Picker onPick={onPick} />)
  expect(screen.getByRole('searchbox', { name: 'Search' })).toHaveFocus()

  await userEvent.keyboard('{ArrowDown}')
  expect(screen.getByRole('button', { name: 'Alpha' })).toHaveFocus()
  await userEvent.keyboard('{ArrowDown}')
  expect(screen.getByRole('button', { name: 'Beta' })).toHaveFocus()

  await userEvent.keyboard('{Enter}')
  expect(onPick).toHaveBeenCalledExactlyOnceWith('Beta')
})

it('stops at the last entry and returns to the search field from the first', async () => {
  render(<Picker onPick={vi.fn()} />)

  await userEvent.keyboard('{ArrowDown}{ArrowDown}{ArrowDown}{ArrowDown}')
  expect(screen.getByRole('button', { name: 'Gamma' })).toHaveFocus()

  await userEvent.keyboard('{ArrowUp}{ArrowUp}')
  expect(screen.getByRole('button', { name: 'Alpha' })).toHaveFocus()
  await userEvent.keyboard('{ArrowUp}')
  expect(screen.getByRole('searchbox', { name: 'Search' })).toHaveFocus()
})

it('still picks the first match on Enter from the search field', async () => {
  const onPick = vi.fn()
  render(<Picker onPick={onPick} />)

  await userEvent.keyboard('ga{Enter}')

  expect(onPick).toHaveBeenCalledExactlyOnceWith('Gamma')
})
