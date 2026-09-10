import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { TopBar } from './TopBar'
import type { SessionInfo } from '../api/types'

const session: SessionInfo = {
  username: 'a.mueller',
  roles: ['Administrator'],
  is_admin: true,
  tb_server_url: 'https://tb:9443/api/',
}

const props = {
  session,
  lang: 'de' as const,
  theme: 'light' as const,
  onToggleTheme: vi.fn(),
  onSetLang: vi.fn(),
  onSignOut: vi.fn(),
}

beforeEach(() => vi.clearAllMocks())

it('carries the wordmark from the artboard', () => {
  render(<TopBar {...props} />)

  // Split across spans so "Bench" can take the TestBench orange, which is
  // why this asks the header for its text rather than for one node.
  expect(screen.getByRole('banner')).toHaveTextContent('TestBench AI Service')
})

it('names the operator and the role the session actually has', () => {
  render(<TopBar {...props} session={{ ...session, is_admin: false }} />)

  expect(screen.getByText('a.mueller')).toBeInTheDocument()
  expect(screen.getByText('Testmanager')).toBeInTheDocument()
})

it('shows where the service answers when status has landed', () => {
  render(<TopBar {...props} serviceLabel="127.0.0.1:8010" />)

  expect(screen.getByText('127.0.0.1:8010')).toBeInTheDocument()
})

it('says nothing about the address before status has landed', () => {
  render(<TopBar {...props} />)

  expect(screen.queryByText(/8010/)).not.toBeInTheDocument()
})

it('labels the theme toggle with what it will do, not with what it shows', async () => {
  render(<TopBar {...props} />)

  await userEvent.click(screen.getByRole('button', { name: 'Dunkles Design' }))

  expect(props.onToggleTheme).toHaveBeenCalled()
})

it('switches the language', async () => {
  render(<TopBar {...props} />)

  await userEvent.click(screen.getByRole('radio', { name: 'EN' }))

  expect(props.onSetLang).toHaveBeenCalledWith('en')
})
