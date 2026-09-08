import { render, screen } from '@testing-library/react'
import { App } from './App'

test('renders the service name', () => {
  render(<App />)
  expect(screen.getByText('TestBench AI Service')).toBeInTheDocument()
})
