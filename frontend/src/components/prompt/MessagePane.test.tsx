import { createRef } from 'react'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

// CM6 needs DOM APIs jsdom lacks. The wrapper holds no logic, so replacing it
// with a textarea costs no coverage. It also renders `diagnostics` as its own
// alert text and exposes the imperative `insert` handle the variable picker
// drives, matching CodeEditor's own real behaviour closely enough for a
// screen test to observe both without a real CM6 view.
vi.mock('../CodeEditor', async () => {
  const { forwardRef, useImperativeHandle } = await import('react')
  return {
    CodeEditor: forwardRef(function MockCodeEditor(
      { value, onChange, ariaLabel, readOnly, diagnostics }: {
        value: string
        onChange: (value: string) => void
        ariaLabel: string
        readOnly?: boolean
        diagnostics?: LintError[]
      },
      ref,
    ) {
      useImperativeHandle(ref, () => ({ insert: (text: string) => onChange(value + text) }), [value, onChange])
      return (
        <div>
          <textarea
            aria-label={ariaLabel}
            value={value}
            readOnly={readOnly}
            onChange={(e) => onChange(e.target.value)}
          />
          {(diagnostics ?? []).map((error, index) => (
            <div key={index} role="alert">{error.message}</div>
          ))}
        </div>
      )
    }),
  }
})

import { MessagePane } from './MessagePane'
import type { CodeEditorHandle } from '../CodeEditor'
import type { LintError, MessageRole, MessageSource, PromptMessageDoc } from '../../api/types'
import type { Lang } from '../../i18n'

function inline(content: string): PromptMessageDoc {
  return { role: 'user', source: 'inline', file: null, content, readable: true }
}

type Overrides = Partial<{
  path: string
  message: PromptMessageDoc
  index: number
  count: number
  readOnly: boolean
  lang: Lang
  diagnostics: LintError[]
  insertable: string[]
  onRemove: () => void
  onMove: (to: number) => void
  onRole: (role: MessageRole) => void
  onContent: (content: string) => void
  onSource: (source: MessageSource) => void
  onFile: (file: string) => void
}>

function setup(overrides: Overrides = {}) {
  const editorRef = createRef<CodeEditorHandle>()
  const props = {
    path: 'prompt.yaml › A › messages[0]',
    message: inline('U'),
    index: 0,
    count: 1,
    readOnly: false,
    lang: 'en' as Lang,
    insertable: [] as string[],
    onRemove: vi.fn(),
    onMove: vi.fn(),
    onRole: vi.fn(),
    onContent: vi.fn(),
    onSource: vi.fn(),
    onFile: vi.fn(),
    ...overrides,
  }
  render(<MessagePane {...props} editorRef={editorRef} />)
  return { ...props, editorRef }
}

describe('MessagePane', () => {
  it('shows where the message text lives', () => {
    setup({ path: 'prompts/de/explainer/sys.jinja' })
    expect(screen.getByText('prompts/de/explainer/sys.jinja')).toBeInTheDocument()
  })

  it('emits a content change', async () => {
    const { onContent } = setup({ message: inline('U') })
    await userEvent.type(screen.getByLabelText('user'), '!')
    expect(onContent).toHaveBeenCalledWith('U!')
  })

  it('emits a role change', async () => {
    const { onRole } = setup()
    await userEvent.selectOptions(screen.getByLabelText(/role/i), 'assistant')
    expect(onRole).toHaveBeenCalledWith('assistant')
  })

  it('emits a move', async () => {
    const { onMove } = setup({ index: 0, count: 2 })
    await userEvent.click(screen.getByRole('button', { name: /move down/i }))
    expect(onMove).toHaveBeenCalledWith(1)
  })

  it('does not offer move up on the first message', () => {
    setup({ index: 0, count: 2 })
    expect(screen.queryByRole('button', { name: /move up/i })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /move down/i })).toBeInTheDocument()
  })

  it('does not offer move down on the last message', () => {
    setup({ index: 1, count: 2 })
    expect(screen.queryByRole('button', { name: /move down/i })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /move up/i })).toBeInTheDocument()
  })

  it('offers no editing controls when read-only', () => {
    setup({ readOnly: true, index: 0, count: 2 })
    expect(screen.queryByRole('button', { name: 'Delete message' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /move (up|down)/i })).not.toBeInTheDocument()
    expect(screen.getByLabelText(/role/i)).toBeDisabled()
  })

  it('removes the message', async () => {
    const { onRemove } = setup()
    await userEvent.click(screen.getByRole('button', { name: 'Delete message' }))
    expect(onRemove).toHaveBeenCalled()
  })

  it('offers the source toggle and reports a switch', async () => {
    const { onSource } = setup({ message: inline('x') })
    await userEvent.selectOptions(screen.getByLabelText('Source'), 'file')
    expect(onSource).toHaveBeenCalledWith('file')
  })

  it('shows an editable file name for a file-backed message', async () => {
    const { onFile } = setup({
      message: { role: 'user', source: 'file', file: 'a_user.jinja', content: 'x', readable: true },
    })
    const field = screen.getByLabelText('File name')
    expect(field).toHaveValue('a_user.jinja')
    await userEvent.clear(field)
    await userEvent.type(field, 'b.jinja')
    expect(onFile).toHaveBeenCalled()
  })

  it('hides both controls when read-only', () => {
    setup({
      readOnly: true,
      message: { role: 'user', source: 'file', file: 'a.jinja', content: 'x', readable: true },
    })
    expect(screen.queryByLabelText('File name')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Source')).not.toBeInTheDocument()
    expect(screen.getByText('a.jinja')).toBeInTheDocument()
  })

  it('marks an unreadable template', () => {
    setup({ message: { role: 'system', source: 'file', file: 'sys.jinja', content: '', readable: false } })
    expect(screen.getByRole('alert')).toHaveTextContent(/sys\.jinja/)
  })

  it('disables the source toggle for an unreadable message and shows why', () => {
    setup({ message: { role: 'system', source: 'file', file: 'sys.jinja', content: '', readable: false } })
    expect(screen.getByLabelText(/source/i)).toBeDisabled()
    expect(screen.getByRole('alert')).toHaveTextContent(/sys\.jinja/)
  })

  it('leaves the source toggle enabled for a readable message', () => {
    setup({ message: { role: 'system', source: 'file', file: 'sys.jinja', content: 'S', readable: true } })
    expect(screen.getByLabelText(/source/i)).toBeEnabled()
  })

  it('feeds diagnostics to the editor', () => {
    setup({ diagnostics: [{ line: 1, column: 0, message: 'bad token' }] })
    expect(screen.getByRole('alert')).toHaveTextContent('bad token')
  })

  it('renders German labels by default', () => {
    const editorRef = createRef<CodeEditorHandle>()
    render(
      <MessagePane
        path="p"
        message={inline('U')}
        index={0}
        count={2}
        readOnly={false}
        insertable={[]}
        editorRef={editorRef}
        onRemove={vi.fn()}
        onMove={vi.fn()}
        onRole={vi.fn()}
        onContent={vi.fn()}
        onSource={vi.fn()}
        onFile={vi.fn()}
      />,
    )
    expect(screen.getByLabelText('Rolle')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Nach unten' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Nachricht löschen' })).toBeInTheDocument()
  })

  it('inserts the chosen variable through the editor handle, then resets the picker', async () => {
    const onContent = vi.fn()
    setup({ onContent, message: inline('Hi '), insertable: ['agent.defect'] })
    await userEvent.selectOptions(screen.getByLabelText('Insert variable…'), 'agent.defect')
    expect(onContent).toHaveBeenCalledWith('Hi {{ agent.defect }}')
    expect(screen.getByLabelText('Insert variable…')).toHaveValue('')
  })

  it('offers no variable picker when read-only', () => {
    setup({ readOnly: true })
    expect(screen.queryByLabelText('Insert variable…')).not.toBeInTheDocument()
  })

  it('offers no variable picker for an unreadable file', () => {
    setup({ message: { role: 'system', source: 'file', file: 'gone.jinja', content: '', readable: false } })
    expect(screen.queryByLabelText('Insert variable…')).not.toBeInTheDocument()
  })
})
