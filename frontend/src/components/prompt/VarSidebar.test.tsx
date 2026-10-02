import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { VarSidebar, type LintState } from './VarSidebar'

const idle: LintState = { running: false, clean: false, error: null, errors: [] }

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
    setup({ lint: { ...idle, errors: [{ line: 3, column: 1, message: 'unexpected end' }] } })
    expect(screen.getByText('Line 3: unexpected end')).toBeInTheDocument()
  })

  it('shows the clean verdict for a clean variant', () => {
    setup({ lint: { ...idle, clean: true } })
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

  describe('with the agent context', () => {
    const agentContext = {
      test_case_set: '<str>',
      test_case_set_obj: { details: { uniqueID: '<str>' }, testCases: [{ index: '<int>' }] },
      typo: '',
    }

    it('lists every field the agent provides, with its type', () => {
      setup({ agentContext })
      expect(screen.getByRole('button', { name: /agent\.test_case_set\s*str/ })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /agent\.test_case_set_obj\s*object/ })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /agent\.typo/ })).toBeInTheDocument()
    })

    it('unfolds an object and inserts its nested path', async () => {
      const props = setup({ agentContext })
      await userEvent.click(screen.getByRole('button', { name: '▸ agent.test_case_set_obj' }))
      await userEvent.click(screen.getByRole('button', { name: '▸ agent.test_case_set_obj.details' }))
      await userEvent.click(screen.getByRole('button', { name: /\.uniqueID/ }))
      expect(props.onInsert).toHaveBeenLastCalledWith('{{ agent.test_case_set_obj.details.uniqueID }}')
    })

    it("shows a list item's fields as a hint, not as an insertable path", async () => {
      setup({ agentContext })
      await userEvent.click(screen.getByRole('button', { name: '▸ agent.test_case_set_obj' }))
      await userEvent.click(screen.getByRole('button', { name: '▸ agent.test_case_set_obj.testCases' }))
      expect(screen.getByText('[].index')).toBeInTheDocument()
      expect(screen.queryByRole('button', { name: /\[\]\.index/ })).not.toBeInTheDocument()
    })
  })
})
