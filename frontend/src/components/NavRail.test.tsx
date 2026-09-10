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

it('offers the agents and projects screens to an admin', () => {
  renderNav(true)

  expect(screen.getByRole('link', { name: /Agenten/ })).toHaveAttribute(
    'href',
    '/admin/agents',
  )
  expect(screen.getByRole('link', { name: /Projekte/ })).toHaveAttribute(
    'href',
    '/admin/projects',
  )
})

it('keeps agents and projects readable for a non-admin', () => {
  // Both screens render read-only for a session without the admin role, the
  // same way Status does — so gating the link would hide information the
  // operator is allowed to see.
  renderNav(false)

  for (const label of [/Agenten/, /Projekte/]) {
    expect(screen.getByRole('link', { name: label })).not.toHaveAttribute(
      'aria-disabled',
      'true',
    )
  }
})

it('badges Projects with the number of overrides in force', () => {
  render(
    <MemoryRouter initialEntries={['/admin/status']}>
      <NavRail lang="de" isAdmin overrideCount={3} />
    </MemoryRouter>,
  )

  expect(screen.getByRole('link', { name: /Projekte/ })).toHaveTextContent('3')
})

it('leaves the badge off when nothing is overridden', () => {
  renderNav(true)

  expect(screen.getByRole('link', { name: /Projekte/ })).toHaveTextContent(/^Projekte$/)
})

it('orders agents and projects after the config sections and before the raw file', () => {
  renderNav(true)
  const labels = screen.getAllByRole('link').map((link) => link.textContent ?? '')
  expect(labels.findIndex((l) => l.includes('Agenten'))).toBeGreaterThan(
    labels.findIndex((l) => l.includes('Protokollierung')),
  )
  expect(labels.findIndex((l) => l.includes('Projekte'))).toBeLessThan(
    labels.findIndex((l) => l.includes('config.toml')),
  )
})
