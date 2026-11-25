import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { TopBar } from './TopBar'
import { DraftProvider, useDraft } from '../state/draft'
import { setUnsavedPrompt } from '../state/unsaved'
import { i18n } from '../i18n'
import type { SessionInfo } from '../api/types'

const session: SessionInfo = {
  username: 'a.mueller',
  roles: ['Administrator'],
  is_admin: true,
  tb_server_url: 'https://tb:9443/api/',
  has_user_key: true,
}

const props = {
  session,
  theme: 'light' as const,
  onToggleTheme: vi.fn(),
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
  expect(screen.getByText('Nur lesend')).toBeInTheDocument()
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

  await userEvent.click(screen.getByRole('button', { name: 'EN' }))

  expect(i18n.language).toBe('en')
  expect(screen.getByRole('button', { name: 'EN' })).toHaveAttribute('aria-pressed', 'true')
})

describe('signing out with something to lose', () => {
  afterEach(() => setUnsavedPrompt(false))

  it('signs out at once when nothing is unsaved', async () => {
    render(<TopBar {...props} />)

    await userEvent.click(screen.getByRole('button', { name: i18n.t('logout') }))

    expect(props.onSignOut).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('asks first while the prompt editor holds unsaved edits', async () => {
    setUnsavedPrompt(true)
    render(<TopBar {...props} />)

    await userEvent.click(screen.getByRole('button', { name: i18n.t('logout') }))

    const dialog = screen.getByRole('dialog')
    expect(dialog).toHaveTextContent(i18n.t('logoutUnsavedPrompt'))
    expect(props.onSignOut).not.toHaveBeenCalled()

    await userEvent.click(screen.getByRole('button', { name: i18n.t('cancel') }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(props.onSignOut).not.toHaveBeenCalled()
  })

  it('asks first while configuration changes are queued, and signs out once confirmed', async () => {
    function Queue() {
      const draft = useDraft()
      return <button onClick={() => draft.setValue('port', 9999)}>queue</button>
    }
    render(
      <DraftProvider saved={{ port: 8010 }}>
        <Queue />
        <TopBar {...props} />
      </DraftProvider>,
    )
    await userEvent.click(screen.getByText('queue'))

    await userEvent.click(screen.getByRole('button', { name: i18n.t('logout') }))

    expect(screen.getByRole('dialog')).toHaveTextContent(
      i18n.t('logoutUnsavedConfig', { count: 1 }),
    )
    await userEvent.click(screen.getByRole('button', { name: i18n.t('logoutAnyway') }))
    expect(props.onSignOut).toHaveBeenCalledTimes(1)
  })
})

it('calls every non-admin read-only, whatever their TestBench role', () => {
  for (const roles of [['ProjectAdministrator'], ['ProjectUser'], ['TestManager']]) {
    const { unmount } = render(
      <TopBar {...props} session={{ ...session, roles, is_admin: false }} />,
    )
    expect(screen.getByText('Nur lesend')).toBeInTheDocument()
    expect(screen.queryByText(/testmanager/i)).not.toBeInTheDocument()
    unmount()
  }
})
