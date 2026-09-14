import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

// CM6 needs DOM APIs jsdom lacks. The wrapper holds no logic, so replacing it
// with a textarea costs no coverage.
//
// The brief's mock types this destructure as `never`; that compiles for the
// mock factory (whose return type vitest widens away) but fails `tsc -b`
// wherever the callback body actually calls `onChange` on it, since `never`
// has no call signatures. Typed to the slice of CodeEditor's own props this
// mock stands in for instead.
vi.mock('./CodeEditor', () => ({
  CodeEditor: ({
    value,
    onChange,
    ariaLabel,
  }: {
    value: string
    onChange: (value: string) => void
    ariaLabel: string
  }) => <textarea aria-label={ariaLabel} value={value} onChange={(e) => onChange(e.target.value)} />,
}))

import { MessageList } from './MessageList'
import type { PromptMessageDoc } from '../api/types'

const messages: PromptMessageDoc[] = [
  { role: 'system', source: 'file', file: 'sys.jinja', content: 'S', readable: true },
  { role: 'user', source: 'inline', file: null, content: 'U', readable: true },
]

const handlers = () => ({
  onAdd: vi.fn(),
  onRemove: vi.fn(),
  onMove: vi.fn(),
  onRole: vi.fn(),
  onContent: vi.fn(),
  onSource: vi.fn(),
  onFile: vi.fn(),
})

// The message's own editable filename field (Task 9) is a text `<input>`,
// which shares the implicit ARIA "textbox" role with the mocked CodeEditor's
// `<textarea>`. Tests that need only the per-message code editors filter
// down to the textarea elements so a file-backed row's filename field
// doesn't shift their indices.
const codeEditors = () => screen.getAllByRole('textbox').filter((el) => el.tagName === 'TEXTAREA')

describe('MessageList', () => {
  it('renders an editor per message', () => {
    render(<MessageList variantName="A" messages={messages} lang="en" {...handlers()} />)
    expect(codeEditors()).toHaveLength(2)
  })

  it('names the file a message comes from', () => {
    render(<MessageList variantName="A" messages={messages} lang="en" {...handlers()} />)
    expect(screen.getByDisplayValue('sys.jinja')).toBeInTheDocument()
  })

  it('marks an unreadable template', () => {
    const broken = [{ ...messages[0], readable: false, content: '' }]
    render(<MessageList variantName="A" messages={broken} lang="en" {...handlers()} />)
    expect(screen.getByRole('alert')).toHaveTextContent(/sys\.jinja/)
  })

  // I3: a message the loader could not read carries an empty placeholder as
  // its `content`, not the file's real body. Letting the operator flip it to
  // "inline" would save that placeholder as the new text and silently
  // truncate the template -- the server's own "readable: false" 409 guard
  // only fires while the message is still `source: "file"`, so the toggle
  // is the console's own responsibility to block.
  it('disables the source toggle for an unreadable message and shows why', () => {
    const broken = [{ ...messages[0], readable: false, content: '' }]
    render(<MessageList variantName="A" messages={broken} lang="en" {...handlers()} />)
    expect(screen.getByLabelText(/source/i)).toBeDisabled()
    expect(screen.getByRole('alert')).toHaveTextContent(/sys\.jinja/)
  })

  it('leaves the source toggle enabled for a readable message', () => {
    const readable = [messages[0]]
    render(<MessageList variantName="A" messages={readable} lang="en" {...handlers()} />)
    expect(screen.getByLabelText(/source/i)).toBeEnabled()
  })

  it('emits a content change', async () => {
    const h = handlers()
    render(<MessageList variantName="A" messages={messages} lang="en" {...h} />)
    await userEvent.type(codeEditors()[1], '!')
    expect(h.onContent).toHaveBeenCalledWith(1, 'U!')
  })

  it('emits a role change', async () => {
    const h = handlers()
    render(<MessageList variantName="A" messages={messages} lang="en" {...h} />)
    await userEvent.selectOptions(screen.getAllByLabelText(/role/i)[1], 'assistant')
    expect(h.onRole).toHaveBeenCalledWith(1, 'assistant')
  })

  it('emits a move', async () => {
    const h = handlers()
    render(<MessageList variantName="A" messages={messages} lang="en" {...h} />)
    await userEvent.click(screen.getAllByRole('button', { name: /move down/i })[0])
    expect(h.onMove).toHaveBeenCalledWith(0, 1)
  })

  it('does not offer move up on the first or move down on the last', () => {
    render(<MessageList variantName="A" messages={messages} lang="en" {...handlers()} />)
    expect(screen.getAllByRole('button', { name: /move up/i })).toHaveLength(1)
    expect(screen.getAllByRole('button', { name: /move down/i })).toHaveLength(1)
  })

  it('offers no editing controls when read-only', () => {
    render(<MessageList variantName="A" messages={messages} lang="en" readOnly {...handlers()} />)
    expect(screen.queryByRole('button', { name: /remove/i })).not.toBeInTheDocument()
  })

  // Task 10's controller ruling: CodeEditor rebuilds its whole CM6 view (undo
  // history, cursor, scroll all discarded) whenever its `ariaLabel` prop
  // changes. A label derived from the message's index would therefore change
  // for every message that shifts position on a reorder, wiping out undo
  // history mid-edit for a message the operator never touched. Pin the label
  // to something that survives a move: it must read the same before and
  // after the message it belongs to changes position.
  it('keeps a message editor accessible name stable across a reorder', () => {
    const h = handlers()
    const { rerender } = render(<MessageList variantName="A" messages={messages} lang="en" {...h} />)
    const beforeLabel = codeEditors()[1].getAttribute('aria-label')

    // Simulate the reorder a move-up/move-down action produces: same two
    // messages, swapped positions.
    rerender(<MessageList variantName="A" messages={[messages[1], messages[0]]} lang="en" {...h} />)
    const afterLabel = codeEditors()[0].getAttribute('aria-label')

    expect(afterLabel).toBe(beforeLabel)
  })

  // The component defaults to German (matching Field.tsx/TriState.tsx's own
  // `lang = 'de'` default) -- every other test above pins lang="en" to keep
  // its English-regex assertions meaningful. This test is the one that
  // actually exercises the German dictionary, so a key present in en.ts but
  // missing (or untranslated) from de.ts would be caught here rather than
  // only by i18n.test.ts's key-parity check.
  it('renders German labels by default', () => {
    render(<MessageList variantName="A" messages={messages} {...handlers()} />)
    expect(screen.getAllByLabelText('Rolle')).toHaveLength(2)
    expect(screen.getByRole('button', { name: 'Nach unten' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Nachricht hinzufügen' })).toBeInTheDocument()
  })

  it('offers the source toggle and reports a switch', async () => {
    const onSource = vi.fn()
    render(
      <MessageList
        variantName="A"
        messages={[{ role: 'user', source: 'inline', file: null, content: 'x', readable: true }]}
        onAdd={vi.fn()}
        onRemove={vi.fn()}
        onMove={vi.fn()}
        onRole={vi.fn()}
        onContent={vi.fn()}
        onSource={onSource}
        onFile={vi.fn()}
      />,
    )
    await userEvent.selectOptions(screen.getByLabelText('Quelle'), 'file')
    expect(onSource).toHaveBeenCalledWith(0, 'file')
  })

  it('shows an editable file name for a file-backed message', async () => {
    const onFile = vi.fn()
    render(
      <MessageList
        variantName="A"
        messages={[{ role: 'user', source: 'file', file: 'a_user.jinja', content: 'x', readable: true }]}
        onAdd={vi.fn()}
        onRemove={vi.fn()}
        onMove={vi.fn()}
        onRole={vi.fn()}
        onContent={vi.fn()}
        onSource={vi.fn()}
        onFile={onFile}
      />,
    )
    const field = screen.getByLabelText('Dateiname')
    expect(field).toHaveValue('a_user.jinja')
    await userEvent.clear(field)
    await userEvent.type(field, 'b.jinja')
    expect(onFile).toHaveBeenCalled()
  })

  it('hides both controls when read-only', () => {
    render(
      <MessageList
        variantName="A"
        readOnly
        messages={[{ role: 'user', source: 'file', file: 'a.jinja', content: 'x', readable: true }]}
        onAdd={vi.fn()}
        onRemove={vi.fn()}
        onMove={vi.fn()}
        onRole={vi.fn()}
        onContent={vi.fn()}
        onSource={vi.fn()}
        onFile={vi.fn()}
      />,
    )
    expect(screen.queryByLabelText('Dateiname')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Quelle')).not.toBeInTheDocument()
    expect(screen.getByText('a.jinja')).toBeInTheDocument()
  })
})
