import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { VarDeclTable } from './VarDeclTable'
import type { PromptVarDecl } from '../api/types'
import { i18n } from '../i18n'
import { chooseOption } from '../test/prime'

// The assertions match the English copy.
beforeEach(() => i18n.changeLanguage('en'))

const decl = (over: Partial<PromptVarDecl> = {}): PromptVarDecl => ({
  name: 'tone',
  description: null,
  value_type: 'string',
  choices: null,
  default_value: null,
  required: false,
  ...over,
})

describe('VarDeclTable', () => {
  it('lists each declaration by key', () => {
    render(
      <VarDeclTable vars={{ tone: decl() }} onAdd={vi.fn()} onEdit={vi.fn()} onRemove={vi.fn()} />,
    )
    expect(screen.getByText('{{ vars.tone }}')).toBeInTheDocument()
  })

  it('shows the choices field only for an enum', () => {
    const { rerender } = render(
      <VarDeclTable vars={{ tone: decl() }} onAdd={vi.fn()} onEdit={vi.fn()} onRemove={vi.fn()} />,
    )
    expect(screen.queryByLabelText(/choices/i)).not.toBeInTheDocument()
    rerender(
      <VarDeclTable
        vars={{ tone: decl({ value_type: 'enum', choices: ['a'] }) }}
        onAdd={vi.fn()}
        onEdit={vi.fn()}
        onRemove={vi.fn()}
      />,
    )
    expect(screen.getByLabelText(/choices/i)).toBeInTheDocument()
  })

  it('reports an enum with no choices as invalid', () => {
    // PromptVariableDefinition requires choices when value_type is enum.
    render(
      <VarDeclTable
        vars={{ tone: decl({ value_type: 'enum', choices: [] }) }}
        onAdd={vi.fn()}
        onEdit={vi.fn()}
        onRemove={vi.fn()}
      />,
    )
    expect(screen.getByRole('alert')).toHaveTextContent(/choices/i)
  })

  it('emits an edit when the type changes', async () => {
    const onEdit = vi.fn()
    render(
      <VarDeclTable vars={{ tone: decl() }} onAdd={vi.fn()} onEdit={onEdit} onRemove={vi.fn()} />,
    )
    await chooseOption(userEvent.setup(), /type/i, 'number')
    expect(onEdit).toHaveBeenCalledWith('tone', expect.objectContaining({ value_type: 'number' }))
  })

  it('emits a removal', async () => {
    const onRemove = vi.fn()
    render(
      <VarDeclTable vars={{ tone: decl() }} onAdd={vi.fn()} onEdit={vi.fn()} onRemove={onRemove} />,
    )
    await userEvent.click(screen.getByRole('button', { name: /remove/i }))
    expect(onRemove).toHaveBeenCalledWith('tone')
  })

  it('offers no add or remove control when read-only', () => {
    render(
      <VarDeclTable
        vars={{ tone: decl() }}
        readOnly
        onAdd={vi.fn()}
        onEdit={vi.fn()}
        onRemove={vi.fn()}
      />,
    )
    expect(screen.queryByRole('button', { name: /remove/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /add/i })).not.toBeInTheDocument()
  })

  // Every other test runs in English to keep its English-regex assertions
  // meaningful. This test is the one that
  // actually exercises the German dictionary, so a key present in en.ts but
  // missing (or untranslated) from de.ts would be caught here rather than
  // only by i18n.test.ts's key-parity check.
  it('renders German labels', async () => {
    await i18n.changeLanguage('de')
    render(
      <VarDeclTable vars={{ tone: decl() }} onAdd={vi.fn()} onEdit={vi.fn()} onRemove={vi.fn()} />,
    )
    expect(screen.getByLabelText('Beschreibung')).toBeInTheDocument()
    expect(screen.getByLabelText('Typ')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Entfernen' })).toBeInTheDocument()
  })
})

describe('adding a variable', () => {
  function renderTable(vars: Record<string, PromptVarDecl> = {}) {
    const onAdd = vi.fn()
    render(<VarDeclTable vars={vars} onAdd={onAdd} onEdit={vi.fn()} onRemove={vi.fn()} />)
    return onAdd
  }
  const TONE: PromptVarDecl = {
    name: 'Tone',
    description: null,
    value_type: 'string',
    choices: null,
    default_value: null,
    required: false,
  }

  it.each(['bad-name', '1bad', 'with space'])('refuses %s and says why', async (name) => {
    const onAdd = renderTable()
    await userEvent.type(screen.getByLabelText(i18n.t('varNewName')), name)

    expect(screen.getByRole('alert')).toHaveTextContent(i18n.t('varNameInvalid'))
    expect(screen.getByRole('button', { name: i18n.t('add') })).toBeDisabled()
    await userEvent.keyboard('{Enter}')
    expect(onAdd).not.toHaveBeenCalled()
  })

  it('says that a name is taken instead of silently emptying the box', async () => {
    const onAdd = renderTable({ tone: TONE })
    const box = screen.getByLabelText(i18n.t('varNewName'))
    await userEvent.type(box, 'tone')

    expect(screen.getByRole('alert')).toHaveTextContent(i18n.t('varNameTaken', { name: 'tone' }))
    await userEvent.keyboard('{Enter}')
    expect(onAdd).not.toHaveBeenCalled()
    expect(box).toHaveValue('tone')
  })

  it('adds a usable name', async () => {
    const onAdd = renderTable({ tone: TONE })
    await userEvent.type(screen.getByLabelText(i18n.t('varNewName')), 'max_findings{Enter}')

    expect(onAdd).toHaveBeenCalledExactlyOnceWith('max_findings')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})

describe('the message for a name that cannot be added', () => {
  it('stands beside the add row, not inside it', async () => {
    render(<VarDeclTable vars={{}} onAdd={vi.fn()} onEdit={vi.fn()} onRemove={vi.fn()} />)
    await userEvent.type(screen.getByLabelText(i18n.t('varNewName')), 'bad-name')

    const message = screen.getByRole('alert')
    // Inside the one-line flex row it took the whole width and left the box 22 px.
    expect(message.closest('form')).toBeNull()
    expect(screen.getByLabelText(i18n.t('varNewName'))).toHaveAttribute(
      'aria-describedby',
      message.id,
    )
  })
})
