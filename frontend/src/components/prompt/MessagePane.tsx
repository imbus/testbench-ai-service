import type { Ref } from 'react'
import { Button } from 'primereact/button'
import { Dropdown } from 'primereact/dropdown'
import { InputText } from 'primereact/inputtext'
import { Message } from 'primereact/message'
import type { LintError, MessageRole, MessageSource, PromptMessageDoc } from '../../api/types'
import { useTranslation } from 'react-i18next'
import { CodeEditor, type CodeEditorHandle } from '../CodeEditor'
import type { CompletionContext } from './templateCompletion'

// A wire token round-tripped through the API, not prose -- kept in English
// regardless of the UI language, matching how Field.tsx never translates `spec.key`.
const ROLES: MessageRole[] = ['system', 'user', 'assistant']

/**
 * A stable accessible name for a message's editor.
 *
 * An index-derived label (`Message ${i + 1}`) would change for every
 * message that shifts position on a move, so a screen reader would announce
 * a different name for the same message. (CodeEditor applies a new label in
 * place; the CodeMirror editor it replaced rebuilt its view, losing undo
 * history -- Task 10's controller ruling.)
 *
 * `role` plus `file` (when file-backed) is stable across a reorder because
 * neither changes when a message's position does. Two messages colliding on
 * this label is acceptable.
 */
function editorLabel(message: PromptMessageDoc): string {
  return message.file ? `${message.role} (${message.file})` : message.role
}

const codeFont = 'var(--font-code)'
const small = { minHeight: 26, fontSize: 12 }
// A label must never separate from its control when the row wraps (Task 10's
// controller ruling) -- each pair is its own no-wrap inline group.
const pair = { display: 'inline-flex', alignItems: 'center', gap: 4, whiteSpace: 'nowrap' } as const

/** The Split layout's centre column: one message's own toolbar and editor. */
export function MessagePane({
  path,
  message,
  index,
  count,
  readOnly,
  diagnostics,
  insertable,
  completion,
  editorRef,
  modelKey,
  keepModels,
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
  diagnostics?: LintError[]
  insertable: string[]
  completion?: CompletionContext
  editorRef: Ref<CodeEditorHandle>
  /** Passed through to `CodeEditor`: one editor model per message tab. */
  modelKey?: string
  keepModels?: string[]
  onRemove: () => void
  onMove: (to: number) => void
  onRole: (role: MessageRole) => void
  onContent: (content: string) => void
  onSource: (source: MessageSource) => void
  onFile: (file: string) => void
}) {
  const { t } = useTranslation()
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
      <div style={{ borderBottom: '1px solid var(--color-divider)' }}>
        {/* Row 1: the message's own path, plus the position/removal controls
            that act on the message as a whole. Task 10's controller ruling:
            one row can't fit path + every control at 1440-1280px, so the
            toolbar is two deliberate rows rather than an undirected wrap. */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '6px 12px 4px', fontSize: 12 }}>
          <span className="text-muted" style={{ fontFamily: codeFont, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', minWidth: 0 }}>
            {path}
          </span>
          <div style={{ flex: 1 }} />
          {!readOnly && index > 0 && (
            <Button type="button" text label={t('moveUp')} style={{ fontSize: 12 }} onClick={() => onMove(index - 1)} />
          )}
          {!readOnly && index < count - 1 && (
            <Button type="button" text label={t('moveDown')} style={{ fontSize: 12 }} onClick={() => onMove(index + 1)} />
          )}
          {/* Hidden on a variant's only message: the reducer refuses to remove
              it (PromptVariant requires one), so the button would do nothing. */}
          {!readOnly && count > 1 && (
            <Button type="button" text severity="danger" label={t('deleteMessage')} style={{ fontSize: 12, color: '#a33a2b' }} onClick={onRemove} />
          )}
        </div>
        {/* Row 2: how the message is edited -- role, source, file name, then
            variable insertion. Each label+control is its own no-wrap group so
            a label never separates from its control if this row itself wraps
            below ~1280px. */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '0 12px 6px', fontSize: 12, flexWrap: 'wrap' }}>
          <div style={pair}>
            {/* No visually-hidden class exists in industry.css (checked); a
                small muted visible label stands in for what would otherwise
                be sr-only. */}
            <label htmlFor={roleId} className="text-muted" style={{ fontSize: 11 }}>
              {t('messageRole')}
            </label>
            <Dropdown
              inputId={roleId}
              disabled={readOnly}
              value={message.role}
              // The `role:` prefix is the prompt.yaml field name, a wire
              // token -- deliberately untranslated, like the role values
              // themselves.
              options={ROLES.map((role) => ({ label: `role: ${role}`, value: role }))}
              onChange={(event) => onRole(event.value as MessageRole)}
              style={small}
            />
          </div>
          {!readOnly && (
            <div style={pair}>
              <label htmlFor={sourceId} style={{ fontSize: 11 }}>
                {t('messageSourceLabel')}
              </label>
              <Dropdown
                inputId={sourceId}
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
                options={[
                  { label: t('messageSourceInline'), value: 'inline' },
                  { label: t('messageSourceFile'), value: 'file' },
                ]}
                onChange={(event) => onSource(event.value as MessageSource)}
                style={small}
              />
            </div>
          )}
          {message.source === 'file' && !readOnly && (
            <div style={pair}>
              <label htmlFor={fileId} style={{ fontSize: 11 }}>
                {t('messageFileLabel')}
              </label>
              <InputText
                id={fileId}
                value={message.file ?? ''}
                onChange={(event) => onFile(event.target.value)}
                style={{ ...small, padding: '1px 6px', width: '26ch', minWidth: '26ch', fontFamily: codeFont }}
              />
            </div>
          )}
          {message.source === 'file' && readOnly && message.file && (
            <span className="text-muted" style={{ fontSize: 11, fontFamily: codeFont }}>
              {message.file}
            </span>
          )}
          {editable && (
            <div style={pair}>
              <label htmlFor={insertId} className="text-muted" style={{ fontSize: 11 }}>
                {t('insertVar')}
              </label>
              {/* Always empty: picking a variable inserts it, and the
                  placeholder is what invites the next pick. */}
              <Dropdown
                inputId={insertId}
                value={null}
                placeholder={t('insertVar')}
                options={insertable.map((name) => ({ label: name, value: name }))}
                style={small}
                onChange={(event) => {
                  const name = event.value as string | null
                  if (!name) return
                  const handle = typeof editorRef === 'object' && editorRef ? editorRef.current : null
                  handle?.insert(`{{ ${name} }}`)
                }}
              />
            </div>
          )}
        </div>
      </div>
      {!message.readable && message.file && (
        <Message
          id={unreadableId}
          severity="error"
          style={{ fontSize: 11, margin: '4px 12px', justifyContent: 'flex-start' }}
          text={
            <>
              {t('messageUnreadable')} <code>{message.file}</code>
            </>
          }
        />
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
          completion={completion}
          modelKey={modelKey}
          keepModels={keepModels}
        />
      </div>
    </div>
  )
}
