import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { VarDeclTable } from './VarDeclTable'
import type { PromptVarDecl } from '../api/types'

const decl = (over: Partial<PromptVarDecl> = {}): PromptVarDecl => ({
  name: 'tone', description: null, value_type: 'string',
  choices: null, default_value: null, required: false, ...over,
})

describe('VarDeclTable', () => {
  it('lists each declaration by key', () => {
    render(<VarDeclTable vars={{ tone: decl() }} onAdd={vi.fn()} onEdit={vi.fn()} onRemove={vi.fn()} />)
    expect(screen.getByDisplayValue('tone')).toBeInTheDocument()
  })

  it('shows the choices field only for an enum', () => {
    const { rerender } = render(
      <VarDeclTable vars={{ tone: decl() }} onAdd={vi.fn()} onEdit={vi.fn()} onRemove={vi.fn()} />,
    )
    expect(screen.queryByLabelText(/choices/i)).not.toBeInTheDocument()
    rerender(
      <VarDeclTable
        vars={{ tone: decl({ value_type: 'enum', choices: ['a'] }) }}
        onAdd={vi.fn()} onEdit={vi.fn()} onRemove={vi.fn()}
      />,
    )
    expect(screen.getByLabelText(/choices/i)).toBeInTheDocument()
  })

  it('reports an enum with no choices as invalid', () => {
    // PromptVariableDefinition requires choices when value_type is enum.
    render(
      <VarDeclTable
        vars={{ tone: decl({ value_type: 'enum', choices: [] }) }}
        onAdd={vi.fn()} onEdit={vi.fn()} onRemove={vi.fn()}
      />,
    )
    expect(screen.getByRole('alert')).toHaveTextContent(/choices/i)
  })

  it('emits an edit when the type changes', async () => {
    const onEdit = vi.fn()
    render(<VarDeclTable vars={{ tone: decl() }} onAdd={vi.fn()} onEdit={onEdit} onRemove={vi.fn()} />)
    await userEvent.selectOptions(screen.getByLabelText(/type/i), 'number')
    expect(onEdit).toHaveBeenCalledWith('tone', expect.objectContaining({ value_type: 'number' }))
  })

  it('emits a removal', async () => {
    const onRemove = vi.fn()
    render(<VarDeclTable vars={{ tone: decl() }} onAdd={vi.fn()} onEdit={vi.fn()} onRemove={onRemove} />)
    await userEvent.click(screen.getByRole('button', { name: /remove/i }))
    expect(onRemove).toHaveBeenCalledWith('tone')
  })

  it('offers no add or remove control when read-only', () => {
    render(<VarDeclTable vars={{ tone: decl() }} readOnly onAdd={vi.fn()} onEdit={vi.fn()} onRemove={vi.fn()} />)
    expect(screen.queryByRole('button', { name: /remove/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /add/i })).not.toBeInTheDocument()
  })
})
