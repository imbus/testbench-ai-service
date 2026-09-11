import { CodeEditor } from './CodeEditor'
import type { LintError, MessageRole, PromptMessageDoc } from '../api/types'

const ROLES: MessageRole[] = ['system', 'user', 'assistant']

/**
 * A stable accessible name for a message's editor.
 *
 * CodeEditor rebuilds its whole CM6 view whenever its `ariaLabel` prop
 * changes -- discarding undo history, cursor position and scroll (Task 10's
 * controller ruling). An index-derived label (`Message ${i + 1}`) would
 * therefore change for every message that shifts position on a move,
 * silently wiping out undo mid-edit for messages the operator never touched.
 *
 * `role` plus `file` (when file-backed) is stable across a reorder because
 * neither changes when a message's position does. Two messages colliding on
 * this label is acceptable -- losing undo history on every move is not.
 */
function editorLabel(message: PromptMessageDoc): string {
  return message.file ? `${message.role} (${message.file})` : message.role
}

function MessageRow({
  index,
  message,
  count,
  readOnly,
  diagnostics,
  onRemove,
  onMove,
  onRole,
  onContent,
}: {
  index: number
  message: PromptMessageDoc
  count: number
  readOnly?: boolean
  diagnostics?: LintError[]
  onRemove: () => void
  onMove: (to: number) => void
  onRole: (role: MessageRole) => void
  onContent: (content: string) => void
}) {
  const roleId = `message-${index}-role`

  return (
    <div
      data-testid="message-row"
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 6,
        padding: '10px 0',
        borderBottom: '1px solid var(--color-divider)',
      }}
    >
      <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          <label htmlFor={roleId} style={{ fontSize: 11 }}>
            Role
          </label>
          <select
            className="input"
            id={roleId}
            disabled={readOnly}
            value={message.role}
            onChange={(event) => onRole(event.target.value as MessageRole)}
          >
            {ROLES.map((role) => (
              <option key={role} value={role}>
                {role}
              </option>
            ))}
          </select>
        </div>
        {message.source === 'file' && message.file && (
          <span
            className="text-muted"
            style={{ fontSize: 11, fontFamily: 'ui-monospace, Menlo, monospace' }}
          >
            {message.file}
          </span>
        )}
        <div style={{ flex: 1 }} />
        {!readOnly && index > 0 && (
          <button type="button" className="btn btn-ghost" onClick={() => onMove(index - 1)}>
            Move up
          </button>
        )}
        {!readOnly && index < count - 1 && (
          <button type="button" className="btn btn-ghost" onClick={() => onMove(index + 1)}>
            Move down
          </button>
        )}
        {!readOnly && (
          <button type="button" className="btn btn-ghost" onClick={onRemove}>
            Remove
          </button>
        )}
      </div>
      {!message.readable && message.file && (
        <span role="alert" style={{ fontSize: 11, color: '#a33a2b' }}>
          {`Could not read ${message.file}.`}
        </span>
      )}
      <CodeEditor
        value={message.content}
        onChange={onContent}
        diagnostics={diagnostics}
        readOnly={readOnly}
        ariaLabel={editorLabel(message)}
      />
    </div>
  )
}

export function MessageList({
  messages,
  readOnly,
  diagnostics,
  onAdd,
  onRemove,
  onMove,
  onRole,
  onContent,
}: {
  messages: PromptMessageDoc[]
  readOnly?: boolean
  /** Lint errors for a message's own template body, keyed by its index. */
  diagnostics?: Record<number, LintError[]>
  onAdd: () => void
  onRemove: (index: number) => void
  onMove: (from: number, to: number) => void
  onRole: (index: number, role: MessageRole) => void
  onContent: (index: number, content: string) => void
}) {
  return (
    <div>
      {messages.map((message, index) => (
        <MessageRow
          key={index}
          index={index}
          message={message}
          count={messages.length}
          readOnly={readOnly}
          diagnostics={diagnostics?.[index]}
          onRemove={() => onRemove(index)}
          onMove={(to) => onMove(index, to)}
          onRole={(role) => onRole(index, role)}
          onContent={(content) => onContent(index, content)}
        />
      ))}
      {!readOnly && (
        <button type="button" className="btn btn-ghost" onClick={onAdd} style={{ marginTop: 10 }}>
          Add message
        </button>
      )}
    </div>
  )
}
