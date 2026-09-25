import type { Ref } from 'react'
import type { LintError, MessageRole, MessageSource, PromptMessageDoc } from '../../api/types'
import { useTranslations, type Lang } from '../../i18n'
import { CodeEditor, type CodeEditorHandle } from '../CodeEditor'

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

const small = { minHeight: 26, padding: '1px 6px', fontSize: 12, width: 'auto' }

/** The Split layout's centre column: one message's own toolbar and editor. */
export function MessagePane({
  path,
  message,
  index,
  count,
  readOnly,
  lang = 'de',
  diagnostics,
  insertable,
  editorRef,
  onRemove,
  onMove,
  onRole,
  onContent,
  onSource,
  onFile,
}: {
  path: string
  message: PromptMessageDoc
  index: number
  count: number
  readOnly: boolean
  lang?: Lang
  diagnostics?: LintError[]
  insertable: string[]
  editorRef: Ref<CodeEditorHandle>
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
  const insertId = `message-${index}-insert`
  const unreadableId = `message-${index}-unreadable`
  const editable = !readOnly && message.readable

  return (
    <div
      data-testid="message-pane"
      style={{ flex: 1, minWidth: 0, minHeight: 0, display: 'flex', flexDirection: 'column' }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          padding: '6px 12px',
          borderBottom: '1px solid var(--color-divider)',
          fontSize: 12,
          flexWrap: 'wrap',
        }}
      >
        <span style={{ fontFamily: 'ui-monospace, Menlo, monospace' }}>{path}</span>
        {/* No visually-hidden class exists in industry.css (checked); a small
            muted visible label stands in for what would otherwise be sr-only. */}
        <label htmlFor={roleId} className="text-muted" style={{ fontSize: 11 }}>
          {t.messageRole}
        </label>
        <select
          className="input"
          id={roleId}
          disabled={readOnly}
          value={message.role}
          onChange={(event) => onRole(event.target.value as MessageRole)}
          style={small}
        >
          {/* The `role:` prefix is the prompt.yaml field name, a wire token --
              deliberately untranslated, like the role values themselves. */}
          {ROLES.map((role) => (
            <option key={role} value={role}>
              role: {role}
            </option>
          ))}
        </select>
        {!readOnly && (
          <>
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
              style={small}
            >
              <option value="inline">{t.messageSourceInline}</option>
              <option value="file">{t.messageSourceFile}</option>
            </select>
          </>
        )}
        {message.source === 'file' && !readOnly && (
          <>
            <label htmlFor={fileId} style={{ fontSize: 11 }}>
              {t.messageFileLabel}
            </label>
            <input
              className="input"
              id={fileId}
              value={message.file ?? ''}
              onChange={(event) => onFile(event.target.value)}
              style={{ ...small, fontFamily: 'ui-monospace, Menlo, monospace' }}
            />
          </>
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
        {editable && (
          <>
            <label htmlFor={insertId} className="text-muted" style={{ fontSize: 11 }}>
              {t.insertVar}
            </label>
            <select
              className="input"
              id={insertId}
              value=""
              style={small}
              onChange={(event) => {
                const name = event.target.value
                if (!name) return
                const handle = typeof editorRef === 'object' && editorRef ? editorRef.current : null
                handle?.insert(`{{ ${name} }}`)
              }}
            >
              <option value="">{t.insertVar}</option>
              {insertable.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </>
        )}
        {!readOnly && index > 0 && (
          <button type="button" className="btn btn-ghost" style={{ fontSize: 12 }} onClick={() => onMove(index - 1)}>
            {t.moveUp}
          </button>
        )}
        {!readOnly && index < count - 1 && (
          <button type="button" className="btn btn-ghost" style={{ fontSize: 12 }} onClick={() => onMove(index + 1)}>
            {t.moveDown}
          </button>
        )}
        {!readOnly && (
          <button type="button" className="btn btn-ghost" style={{ fontSize: 12, color: '#a33a2b' }} onClick={onRemove}>
            {t.deleteMessage}
          </button>
        )}
      </div>
      {!message.readable && message.file && (
        <span id={unreadableId} role="alert" style={{ fontSize: 11, color: '#a33a2b', padding: '4px 12px' }}>
          {t.messageUnreadable} <code>{message.file}</code>
        </span>
      )}
      <div style={{ flex: 1, minHeight: 0 }}>
        <CodeEditor
          ref={editorRef}
          fill
          value={message.content}
          onChange={onContent}
          diagnostics={diagnostics}
          readOnly={readOnly}
          ariaLabel={editorLabel(message)}
        />
      </div>
    </div>
  )
}
