import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { NavRail } from './NavRail'

const renderNav = (isAdmin: boolean) =>
  render(
    <MemoryRouter initialEntries={['/admin/status']}>
      <NavRail lang="de" isAdmin={isAdmin} />
    </MemoryRouter>,
  )

test('renders every phase 1 destination', () => {
  renderNav(true)
  for (const label of ['Status', 'Dienst', 'LLM-Anbieter', 'Protokollierung']) {
    expect(screen.getByRole('link', { name: new RegExp(label) })).toBeInTheDocument()
  }
})

test('marks restricted destinations for a non-admin', () => {
  renderNav(false)
  const link = screen.getByRole('link', { name: /Dienst/ })
  expect(link).toHaveAttribute('aria-disabled', 'true')
})

test('leaves Status open to a non-admin', () => {
  renderNav(false)
  expect(screen.getByRole('link', { name: /Status/ })).not.toHaveAttribute(
    'aria-disabled',
    'true',
  )
})

test('an admin has nothing disabled', () => {
  renderNav(true)
  for (const link of screen.getAllByRole('link')) {
    expect(link).not.toHaveAttribute('aria-disabled', 'true')
  }
})

it('offers the raw config screen to an admin', () => {
  renderNav(true)

  expect(screen.getByRole('link', { name: /config\.toml/ })).toHaveAttribute(
    'href',
    '/admin/raw',
  )
})

it('marks the raw config screen restricted for a non-admin', () => {
  renderNav(false)

  expect(screen.getByRole('link', { name: /config\.toml/ })).toHaveAttribute(
    'aria-disabled',
    'true',
  )
})
