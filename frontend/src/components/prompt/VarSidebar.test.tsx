import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { VarSidebar, type LintState } from './VarSidebar'

const idle: LintState = { running: false, checked: false, error: null, errors: [] }

function setup(overrides: Partial<Parameters<typeof VarSidebar>[0]> = {}) {
  const props = {
    agentVars: ['agent.defect', 'agent.test_case'],
    declaredVars: ['vars.tone'],
    used: ['agent.defect'],
    undeclared: [],
    canInsert: true,
    canDeclare: true,
    lint: idle,
    lang: 'en' as const,
    onInsert: vi.fn(),
    onDeclare: vi.fn(),
    onLint: vi.fn(),
    ...overrides,
  }
  render(<VarSidebar {...props} />)
  return props
}

describe('VarSidebar', () => {
  it('inserts a variable wrapped in an expression tag', async () => {
    const props = setup()
    await userEvent.click(screen.getByRole('button', { name: /agent\.test_case/ }))
    expect(props.onInsert).toHaveBeenCalledWith('{{ agent.test_case }}')
  })

  it('marks used variables', () => {
    setup()
    expect(screen.getByRole('button', { name: /agent\.defect/ })).toHaveAttribute('data-used', 'true')
    expect(screen.getByRole('button', { name: /vars\.tone/ })).toHaveAttribute('data-used', 'false')
  })

  it('disables insertion when the editor cannot take it', () => {
    setup({ canInsert: false })
    expect(screen.getByRole('button', { name: /agent\.defect/ })).toBeDisabled()
  })

  it('offers to declare undeclared vars, admin only', async () => {
    const props = setup({ undeclared: ['depth'] })
    expect(screen.getByText('depth')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'declare' }))
    expect(props.onDeclare).toHaveBeenCalled()
  })

  it('hides the declare button for a non-admin', () => {
    setup({ undeclared: ['depth'], canDeclare: false })
    expect(screen.queryByRole('button', { name: 'declare' })).not.toBeInTheDocument()
  })

  it('shows lint errors by line', () => {
    setup({ lint: { ...idle, checked: true, errors: [{ line: 3, column: 1, message: 'unexpected end' }] } })
    expect(screen.getByText('Line 3: unexpected end')).toBeInTheDocument()
  })

  it('shows the clean result only after a check', () => {
    setup({ lint: { ...idle, checked: true } })
    expect(screen.getByText(/No syntax errors\./)).toBeInTheDocument()
  })

  it('shows no result before a check', () => {
    setup()
    expect(screen.queryByText(/No syntax errors\./)).not.toBeInTheDocument()
  })

  it('runs lint on demand and surfaces a failed run', async () => {
    const props = setup({ lint: { ...idle, error: 'boom' } })
    await userEvent.click(screen.getByRole('button', { name: /^lint$/i }))
    expect(props.onLint).toHaveBeenCalled()
    expect(screen.getByRole('alert')).toHaveTextContent('boom')
  })

  it('renders no Lint button as the Tabs drawer (the status bar owns lint there)', () => {
    setup({ variant: 'drawer' })
    expect(screen.queryByRole('button', { name: /^lint$/i })).not.toBeInTheDocument()
  })
})
