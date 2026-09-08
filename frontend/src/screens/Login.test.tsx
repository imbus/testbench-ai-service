import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Login } from './Login'

const props = {
  serverUrl: 'https://tb.example.com:9443/api/',
  lang: 'de' as const,
  onSignIn: vi.fn(),
  error: null,
  busy: false,
}

beforeEach(() => vi.clearAllMocks())

test('shows the configured server read-only', () => {
  render(<Login {...props} />)
  const field = screen.getByLabelText('TestBench-Server')
  expect(field).toHaveValue('https://tb.example.com:9443/api/')
  expect(field).toHaveAttribute('readonly')
})

test('submits the credentials', async () => {
  render(<Login {...props} />)
  await userEvent.type(screen.getByLabelText('Benutzername'), 'a.mueller')
  await userEvent.type(screen.getByLabelText('Passwort'), 'secret')
  await userEvent.click(screen.getByRole('button', { name: 'Mit TestBench anmelden' }))
  await waitFor(() =>
    expect(props.onSignIn).toHaveBeenCalledWith('a.mueller', 'secret'),
  )
})

test('does not submit an empty form', async () => {
  render(<Login {...props} />)
  await userEvent.click(screen.getByRole('button', { name: 'Mit TestBench anmelden' }))
  expect(props.onSignIn).not.toHaveBeenCalled()
})

test('shows a sign-in error', () => {
  render(<Login {...props} error="Invalid credentials" />)
  expect(screen.getByRole('alert')).toHaveTextContent('Invalid credentials')
})

test('has no role selector', () => {
  /** The prototype's role picker was labelled "(demo)"; roles come from TestBench. */
  render(<Login {...props} />)
  expect(screen.queryByLabelText(/rolle/i)).toBeNull()
})

test('disables the button while signing in', () => {
  render(<Login {...props} busy />)
  expect(screen.getByRole('button', { name: 'Mit TestBench anmelden' })).toBeDisabled()
})
