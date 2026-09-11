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
  onAdd: vi.fn(), onRemove: vi.fn(), onMove: vi.fn(), onRole: vi.fn(), onContent: vi.fn(),
})

describe('MessageList', () => {
  it('renders an editor per message', () => {
    render(<MessageList messages={messages} lang="en" {...handlers()} />)
    expect(screen.getAllByRole('textbox')).toHaveLength(2)
  })

  it('names the file a message comes from', () => {
    render(<MessageList messages={messages} lang="en" {...handlers()} />)
    expect(screen.getByText('sys.jinja')).toBeInTheDocument()
  })

  it('marks an unreadable template', () => {
    const broken = [{ ...messages[0], readable: false, content: '' }]
    render(<MessageList messages={broken} lang="en" {...handlers()} />)
    expect(screen.getByRole('alert')).toHaveTextContent(/sys\.jinja/)
  })

  it('emits a content change', async () => {
    const h = handlers()
    render(<MessageList messages={messages} lang="en" {...h} />)
    await userEvent.type(screen.getAllByRole('textbox')[1], '!')
    expect(h.onContent).toHaveBeenCalledWith(1, 'U!')
  })

  it('emits a role change', async () => {
    const h = handlers()
    render(<MessageList messages={messages} lang="en" {...h} />)
    await userEvent.selectOptions(screen.getAllByLabelText(/role/i)[1], 'assistant')
    expect(h.onRole).toHaveBeenCalledWith(1, 'assistant')
  })

  it('emits a move', async () => {
    const h = handlers()
    render(<MessageList messages={messages} lang="en" {...h} />)
    await userEvent.click(screen.getAllByRole('button', { name: /move down/i })[0])
    expect(h.onMove).toHaveBeenCalledWith(0, 1)
  })

  it('does not offer move up on the first or move down on the last', () => {
    render(<MessageList messages={messages} lang="en" {...handlers()} />)
    expect(screen.getAllByRole('button', { name: /move up/i })).toHaveLength(1)
    expect(screen.getAllByRole('button', { name: /move down/i })).toHaveLength(1)
  })

  it('offers no editing controls when read-only', () => {
    render(<MessageList messages={messages} lang="en" readOnly {...handlers()} />)
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
    const { rerender } = render(<MessageList messages={messages} lang="en" {...h} />)
    const beforeLabel = screen.getAllByRole('textbox')[1].getAttribute('aria-label')

    // Simulate the reorder a move-up/move-down action produces: same two
    // messages, swapped positions.
    rerender(<MessageList messages={[messages[1], messages[0]]} lang="en" {...h} />)
    const afterLabel = screen.getAllByRole('textbox')[0].getAttribute('aria-label')

    expect(afterLabel).toBe(beforeLabel)
  })

  // The component defaults to German (matching Field.tsx/TriState.tsx's own
  // `lang = 'de'` default) -- every other test above pins lang="en" to keep
  // its English-regex assertions meaningful. This test is the one that
  // actually exercises the German dictionary, so a key present in en.ts but
  // missing (or untranslated) from de.ts would be caught here rather than
  // only by i18n.test.ts's key-parity check.
  it('renders German labels by default', () => {
    render(<MessageList messages={messages} {...handlers()} />)
    expect(screen.getAllByLabelText('Rolle')).toHaveLength(2)
    expect(screen.getByRole('button', { name: 'Nach unten' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Nachricht hinzufügen' })).toBeInTheDocument()
  })
})
