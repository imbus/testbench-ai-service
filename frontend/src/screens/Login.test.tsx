import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Login } from './Login'

const props = {
  serverUrl: 'https://tb.example.com:9443/api/',
  lang: 'de' as const,
  theme: 'light' as const,
  onSignIn: vi.fn(),
  onSetLang: vi.fn(),
  onToggleTheme: vi.fn(),
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

test('carries the brand lockup from the artboard', () => {
  render(<Login {...props} />)
  expect(document.body).toHaveTextContent('TestBench AI Service')
  expect(document.body).toHaveTextContent('Konfigurationskonsole')
})

test('offers the language and theme controls before sign-in', async () => {
  // Both are the artboard's, and both have to work unauthenticated: an
  // operator who cannot read the German login form has no way past it.
  render(<Login {...props} />)

  await userEvent.click(screen.getByRole('radio', { name: 'EN' }))
  expect(props.onSetLang).toHaveBeenCalledWith('en')

  await userEvent.click(screen.getByRole('button', { name: 'Dunkles Design' }))
  expect(props.onToggleTheme).toHaveBeenCalled()
})

test('disables the button while signing in', () => {
  render(<Login {...props} busy />)
  expect(screen.getByRole('button', { name: 'Mit TestBench anmelden' })).toBeDisabled()
})
