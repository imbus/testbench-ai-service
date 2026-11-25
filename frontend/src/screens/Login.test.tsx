import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Login } from './Login'
import { i18n } from '../i18n'
import { ApiError } from '../api/client'

const props = {
  theme: 'light' as const,
  onSignIn: vi.fn(),
  onToggleTheme: vi.fn(),
  error: null,
  busy: false,
}

beforeEach(() => vi.clearAllMocks())

test('does not show the TestBench server', () => {
  render(<Login {...props} />)
  expect(screen.queryByLabelText('TestBench-Server')).toBeNull()
  expect(document.body).not.toHaveTextContent('tb.example.com')
})

test('submits the credentials', async () => {
  render(<Login {...props} />)
  await userEvent.type(screen.getByLabelText('Benutzername'), 'a.mueller')
  await userEvent.type(screen.getByLabelText('Passwort'), 'secret')
  await userEvent.click(screen.getByRole('button', { name: 'Mit TestBench anmelden' }))
  await waitFor(() => expect(props.onSignIn).toHaveBeenCalledWith('a.mueller', 'secret'))
})

test('does not submit an empty form, and says what is missing', async () => {
  render(<Login {...props} />)
  await userEvent.click(screen.getByRole('button', { name: 'Mit TestBench anmelden' }))

  expect(props.onSignIn).not.toHaveBeenCalled()
  expect(screen.getByText('Bitte Benutzername und Passwort eingeben.')).toBeInTheDocument()
  expect(screen.getByLabelText('Benutzername')).toHaveFocus()
  expect(screen.getByLabelText('Benutzername')).toHaveAttribute('aria-invalid', 'true')
})

test('puts the cursor in the password field when only that is missing', async () => {
  render(<Login {...props} />)
  await userEvent.type(screen.getByLabelText('Benutzername'), 'a.mueller')
  await userEvent.click(screen.getByRole('button', { name: 'Mit TestBench anmelden' }))

  expect(props.onSignIn).not.toHaveBeenCalled()
  expect(screen.getByLabelText('Passwort')).toHaveFocus()
  expect(screen.getByLabelText('Benutzername')).not.toHaveAttribute('aria-invalid')
})

test('the missing-fields notice goes away once the operator types', async () => {
  render(<Login {...props} />)
  await userEvent.click(screen.getByRole('button', { name: 'Mit TestBench anmelden' }))
  await userEvent.type(screen.getByLabelText('Benutzername'), 'a')

  expect(screen.queryByText('Bitte Benutzername und Passwort eingeben.')).not.toBeInTheDocument()
})

test('explains that the previous session ended', () => {
  render(<Login {...props} expired />)

  expect(
    screen.getByText('Die Sitzung ist abgelaufen oder wurde beendet. Bitte erneut anmelden.'),
  ).toBeInTheDocument()
})

test('says nothing about an expired session on an ordinary visit', () => {
  render(<Login {...props} />)

  expect(screen.queryByText(/abgelaufen/)).not.toBeInTheDocument()
})

test('shows wrong credentials without technical details', () => {
  render(<Login {...props} error={new ApiError('Invalid credentials', 401)} />)
  expect(screen.getByRole('alert')).toHaveTextContent('Benutzername oder Passwort ist falsch.')
  expect(screen.queryByText('Details')).toBeNull()
})

test('explains an unreachable TestBench and keeps the cause under details', () => {
  const cause = 'Could not connect to TestBench server: HTTPSConnectionPool(...)'
  render(<Login {...props} error={new ApiError(cause, 502)} />)
  const alert = screen.getByRole('alert')
  expect(alert).toHaveTextContent('Der TestBench-Server ist nicht erreichbar.')
  expect(screen.getByText('Details')).toBeInTheDocument()
  expect(screen.getByText(cause)).not.toBeVisible()
})

test('has no role selector', () => {
  /** The prototype's role picker was labelled "(demo)"; roles come from TestBench. */
  render(<Login {...props} />)
  expect(screen.queryByLabelText(/rolle/i)).toBeNull()
})

test('carries the brand lockup from the artboard', () => {
  render(<Login {...props} />)
  expect(document.body).toHaveTextContent('TestBench AI Service')
  expect(document.body).toHaveTextContent('Konfigurationskonsole')
})

test('offers the language and theme controls before sign-in', async () => {
  // Both are the artboard's, and both have to work unauthenticated: an
  // operator who cannot read the German login form has no way past it.
  render(<Login {...props} />)

  await userEvent.click(screen.getByRole('button', { name: 'Dunkles Design' }))
  expect(props.onToggleTheme).toHaveBeenCalled()

  await userEvent.click(screen.getByRole('button', { name: 'EN' }))
  expect(i18n.language).toBe('en')
  expect(screen.getByRole('button', { name: 'Sign in with TestBench' })).toBeInTheDocument()
})

test('disables the button while signing in', () => {
  render(<Login {...props} busy />)
  expect(screen.getByRole('button', { name: 'Mit TestBench anmelden' })).toBeDisabled()
})

test('a wrong-password message does not come back after an empty submit and a keystroke', async () => {
  const wrong = new ApiError('Invalid credentials', 401)
  render(<Login {...props} error={wrong} />)
  expect(screen.getByText('Benutzername oder Passwort ist falsch.')).toBeInTheDocument()

  // Nothing typed yet: the empty submit explains itself instead.
  await userEvent.click(screen.getByRole('button', { name: 'Mit TestBench anmelden' }))
  expect(screen.getByText('Bitte Benutzername und Passwort eingeben.')).toBeInTheDocument()

  await userEvent.type(screen.getByLabelText('Benutzername'), 'a')

  expect(screen.queryByText('Bitte Benutzername und Passwort eingeben.')).not.toBeInTheDocument()
  expect(screen.queryByText('Benutzername oder Passwort ist falsch.')).not.toBeInTheDocument()
})

test('editing a field takes the answer to the previous attempt away', async () => {
  render(<Login {...props} error={new ApiError('Invalid credentials', 401)} />)

  await userEvent.type(screen.getByLabelText('Passwort'), 'x')

  expect(screen.queryByText('Benutzername oder Passwort ist falsch.')).not.toBeInTheDocument()
})

test('a new failed attempt shows its own message again', async () => {
  const { rerender } = render(<Login {...props} error={new ApiError('Invalid credentials', 401)} />)
  await userEvent.type(screen.getByLabelText('Passwort'), 'x')

  rerender(<Login {...props} error={new ApiError('Invalid credentials', 401)} />)

  expect(screen.getByText('Benutzername oder Passwort ist falsch.')).toBeInTheDocument()
})
