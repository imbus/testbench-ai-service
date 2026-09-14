import { CodeEditor } from './CodeEditor'
import { useTranslations, type Lang } from '../i18n'
import type { LintError, MessageRole, MessageSource, PromptMessageDoc } from '../api/types'

// A wire token round-tripped through the API, not prose -- kept in English
// regardless of `lang`, matching how Field.tsx never translates `spec.key`.
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
  lang,
  diagnostics,
  onRemove,
  onMove,
  onRole,
  onContent,
  onSource,
  onFile,
}: {
  index: number
  message: PromptMessageDoc
  count: number
  readOnly?: boolean
  lang: Lang
  diagnostics?: LintError[]
  onRemove: () => void
  onMove: (to: number) => void
  onRole: (role: MessageRole) => void
  onContent: (content: string) => void
  onSource: (source: MessageSource) => void
  onFile: (file: string) => void
}) {
  const t = useTranslations(lang)
  const roleId = `message-${index}-role`
  const sourceId = `message-${index}-source`
  const fileId = `message-${index}-file`
  const unreadableId = `message-${index}-unreadable`

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
            {t.messageRole}
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
        {!readOnly && (
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            <label htmlFor={sourceId} style={{ fontSize: 11 }}>
              {t.messageSourceLabel}
            </label>
            <select
              className="input"
              id={sourceId}
              value={message.source}
              // I3: the server refuses to save a "readable: false" file-backed
              // message with a 409 (the loader's placeholder is an empty
              // body, not the template's real text), but that guard only
              // fires while the message is still `source: "file"`. Flipping
              // it to "inline" here would carry the same empty placeholder
              // in as the new inline text and walk straight around the
              // guard -- the save would go through and silently truncate the
              // template. Disabled outright rather than only the "inline"
              // option: there is nothing useful to switch to until the file
              // is readable again.
              disabled={!message.readable}
              aria-describedby={!message.readable ? unreadableId : undefined}
              onChange={(event) => onSource(event.target.value as MessageSource)}
            >
              <option value="inline">{t.messageSourceInline}</option>
              <option value="file">{t.messageSourceFile}</option>
            </select>
          </div>
        )}
        {message.source === 'file' && !readOnly && (
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            <label htmlFor={fileId} style={{ fontSize: 11 }}>
              {t.messageFileLabel}
            </label>
            <input
              className="input"
              id={fileId}
              value={message.file ?? ''}
              onChange={(event) => onFile(event.target.value)}
              style={{ fontFamily: 'ui-monospace, Menlo, monospace' }}
            />
          </div>
        )}
        {message.source === 'file' && readOnly && message.file && (
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
            {t.moveUp}
          </button>
        )}
        {!readOnly && index < count - 1 && (
          <button type="button" className="btn btn-ghost" onClick={() => onMove(index + 1)}>
            {t.moveDown}
          </button>
        )}
        {!readOnly && (
          <button type="button" className="btn btn-ghost" onClick={onRemove}>
            {t.remove}
          </button>
        )}
      </div>
      {!message.readable && message.file && (
        <span id={unreadableId} role="alert" style={{ fontSize: 11, color: '#a33a2b' }}>
          {t.messageUnreadable} <code>{message.file}</code>
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
  variantName,
  messages,
  readOnly,
  lang = 'de',
  diagnostics,
  onAdd,
  onRemove,
  onMove,
  onRole,
  onContent,
  onSource,
  onFile,
}: {
  variantName: string
  messages: PromptMessageDoc[]
  readOnly?: boolean
  lang?: Lang
  /** Lint errors for a message's own template body, keyed by its index. */
  diagnostics?: Record<number, LintError[]>
  onAdd: () => void
  onRemove: (index: number) => void
  onMove: (from: number, to: number) => void
  onRole: (index: number, role: MessageRole) => void
  onContent: (index: number, content: string) => void
  onSource: (index: number, source: MessageSource) => void
  onFile: (index: number, file: string) => void
}) {
  const t = useTranslations(lang)

  return (
    <div>
      {messages.map((message, index) => (
        <MessageRow
          key={index}
          index={index}
          message={message}
          count={messages.length}
          readOnly={readOnly}
          lang={lang}
          diagnostics={diagnostics?.[index]}
          onRemove={() => onRemove(index)}
          onMove={(to) => onMove(index, to)}
          onRole={(role) => onRole(index, role)}
          onContent={(content) => onContent(index, content)}
          onSource={(source) => onSource(index, source)}
          onFile={(file) => onFile(index, file)}
        />
      ))}
      {!readOnly && (
        <button type="button" className="btn btn-ghost" onClick={onAdd} style={{ marginTop: 10 }}>
          {t.addMessage}
        </button>
      )}
    </div>
  )
}
