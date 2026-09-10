import { lastSegment } from '../api/paths'
import { useEffect, useState } from 'react'
import { useTranslations, type Lang } from '../i18n'
import type { FieldSpec } from '../screens/fields'
import { useDraft } from '../state/draft'

/** Turn the current draft value (or the saved one) into text for an input. */
function asText(value: unknown): string {
  if (value === null || value === undefined) return ''
  if (Array.isArray(value)) return value.join(', ')
  return String(value)
}

/** How an inherited value reads in the note above an un-overridden control. */
function asNote(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  if (Array.isArray(value)) return value.length ? value.join(', ') : '—'
  return String(value)
}

export function Field({
  spec,
  saved,
  issue,
  inheritedFrom,
  lang = 'de',
}: {
  spec: FieldSpec
  /** The value as saved on disk — what an unedited field shows. */
  saved: unknown
  /** A server-side validation message addressed to this field, if any. */
  issue?: string
  /**
   * Turns this field into a per-project override control (design §5.4).
   *
   * `value` is what applies when this project says nothing, and `label` names
   * where that comes from ("global"). A project override in `config.toml` is
   * sparse, so "says nothing" and "says false" are different settings and must
   * not look the same: without this, an operator could set an override and
   * never find the way back off it.
   *
   * Needs no new overlay semantics (design §3.8). The three states the draft
   * already has are exactly the three this renders: no edit and no saved value
   * = inherit, a value = override, a queued `null` = remove the key and go
   * back to inheriting.
   */
  inheritedFrom?: { value: unknown; label: string }
  lang?: Lang
}) {
  const t = useTranslations(lang)
  const draft = useDraft()
  const draftValue = draft.valueOf(spec.key, saved)
  const changed = draft.isChanged(spec.key)
  const issueId = `${spec.key}-issue`

  // Overridden means "this scope has an opinion": a draft edit that is not a
  // queued removal, or -- absent any edit -- a value already on disk. A `null`
  // edit is a queued removal, which is the operator asking to inherit again.
  const overridden = changed ? draftValue !== null : saved !== undefined
  const inheriting = inheritedFrom !== undefined && !overridden

  // While inheriting, a switch or select displays the value that actually
  // applies: an empty control would read as "off"/"unset", which is a
  // different setting from "inherits a global true", and toggling a switch has
  // to move away from what is displayed, not from `undefined`.
  const value = inheriting ? inheritedFrom.value : draftValue

  // Text-like controls are the opposite: they render EMPTY while inheriting,
  // with the inherited value as a placeholder, because an empty box is what
  // "no override here" looks like. Pre-filling them would make the field
  // impossible to type over -- clearing it queues a removal, which is still
  // "inheriting", which puts the value straight back and the next keystroke
  // appends to it.
  const inputText = inheriting ? '' : asText(value)
  const placeholder = inheriting ? asText(inheritedFrom.value) || undefined : undefined

  // The list type needs to hold raw text locally while editing. Without this,
  // a trailing comma produces an array whose join() has no comma, so the comma
  // can never persist in the displayed value — the next character appends to
  // the previous entry. Text and number and select types don't need this
  // because they round-trip through asText() identically.
  const [text, setText] = useState<string | null>(null)

  // When the edit goes away (Revert or Discard all), clear the local text state
  // so the input re-syncs to show the saved value or parsed draft value.
  useEffect(() => {
    if (!changed) {
      setText(null)
    }
  }, [changed])

  /**
   * An empty input means "remove this key", never the empty string.
   *
   * Every optional field in AppConfig is `X | None` with a meaningful default;
   * writing `""` would either fail validation (`ssl_cert = ""` is not a file)
   * or persist a value the operator meant to clear.
   */
  const commit = (raw: string, parse: (text: string) => unknown) => {
    if (raw.trim() === '') {
      draft.unsetValue(spec.key)
      return
    }
    draft.setValue(spec.key, parse(raw))
  }

  const control = () => {
    switch (spec.type) {
      case 'bool':
        return (
          <button
            type="button"
            role="switch"
            id={spec.key}
            aria-checked={value === true}
            aria-labelledby={`${spec.key}-label`}
            aria-invalid={issue ? true : undefined}
            aria-describedby={issue ? issueId : undefined}
            onClick={() => draft.setValue(spec.key, value !== true)}
            style={{
              width: 36,
              height: 20,
              borderRadius: 10,
              border: '1px solid var(--color-divider)',
              background: value === true ? 'var(--color-accent)' : 'var(--color-surface)',
              position: 'relative',
              cursor: 'pointer',
              padding: 0,
            }}
          >
            <span
              style={{
                position: 'absolute',
                top: 2,
                left: value === true ? 18 : 2,
                width: 14,
                height: 14,
                borderRadius: 7,
                background: value === true ? '#fff' : 'var(--color-text)',
                transition: 'left .15s',
              }}
            />
          </button>
        )
      case 'select':
        return (
          <select
            className="input"
            id={spec.key}
            aria-invalid={issue ? true : undefined}
            aria-describedby={issue ? issueId : undefined}
            value={asText(value)}
            onChange={(event) => draft.setValue(spec.key, event.target.value)}
          >
            {(spec.options ?? []).map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        )
      case 'number':
        return (
          <input
            className="input"
            id={spec.key}
            type="number"
            aria-invalid={issue ? true : undefined}
            aria-describedby={issue ? issueId : undefined}
            placeholder={placeholder}
            value={inputText}
            onChange={(event) =>
              commit(event.target.value, (text) => {
                const parsed = Number(text)
                // A half-typed "1e" parses to NaN, which JSON.stringify turns
                // into null and the server would read as a removal. Keep the
                // raw text instead and let the server's validation say so.
                return Number.isNaN(parsed) ? text : parsed
              })
            }
          />
        )
      case 'textarea':
        return (
          <textarea
            className="input"
            id={spec.key}
            rows={4}
            aria-invalid={issue ? true : undefined}
            aria-describedby={issue ? issueId : undefined}
            placeholder={placeholder}
            value={inputText}
            onChange={(event) => commit(event.target.value, (text) => text)}
            style={{ resize: 'vertical', fontFamily: 'inherit' }}
          />
        )
      case 'list':
        return (
          <input
            className="input"
            id={spec.key}
            aria-invalid={issue ? true : undefined}
            aria-describedby={issue ? issueId : undefined}
            placeholder={placeholder}
            value={text ?? inputText}
            onChange={(event) => {
              const raw = event.target.value
              setText(raw)
              commit(raw, (text) =>
                text
                  .split(',')
                  .map((entry) => entry.trim())
                  .filter((entry) => entry !== ''),
              )
            }}
          />
        )
      default:
        return (
          <input
            className="input"
            id={spec.key}
            type="text"
            aria-invalid={issue ? true : undefined}
            aria-describedby={issue ? issueId : undefined}
            placeholder={placeholder}
            value={inputText}
            onChange={(event) => commit(event.target.value, (text) => text)}
          />
        )
    }
  }

  return (
    // The grid, gap, padding and label styling deliberately match
    // ReadOnlyField exactly: the two render the same form for different
    // sessions, and a different metric here would make the Service screen
    // jump when an admin signs in.
    <div
      data-testid="field-row"
      // Read by the override tests and by the styling below. A row with no
      // `inheritedFrom` is always "overridden": global scope inherits from
      // nothing, so styling it as inherited would be a claim about the config
      // that is not true.
      data-overridden={inheritedFrom === undefined ? 'true' : String(overridden)}
      style={{
        display: 'grid',
        gridTemplateColumns: 'minmax(180px, 260px) 1fr',
        gap: 16,
        padding: '10px 0',
        borderBottom: '1px solid var(--color-divider)',
        alignItems: 'start',
      }}
    >
      <div>
        <label
          id={`${spec.key}-label`}
          htmlFor={spec.key}
          // The last segment only, as ReadOnlyField shows it: the section is
          // already in the screen's subheading, so 'llm_config.model' would
          // read as 'llm_config.' twice. The id and htmlFor stay the full
          // dotted key, which is what makes them unique on a screen.
          style={{ fontSize: 13, fontFamily: 'ui-monospace, Menlo, monospace', display: 'block' }}
        >
          {spec.label ?? lastSegment(spec.key)}
        </label>
        <span className="text-muted" style={{ fontSize: 11 }}>
          {spec.hint}
        </span>
      </div>
      <div
        style={{
          maxWidth: 480,
          display: 'flex',
          flexDirection: 'column',
          gap: 4,
          // Visibly not-overridden, so a project's own settings stand out from
          // the ones it merely inherits.
          opacity: inheriting ? 0.65 : 1,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          {control()}
          {/* Only when there is an override to clear. A queued removal is
              already "inheriting", and offering it again would write the same
              null twice. */}
          {inheritedFrom !== undefined && overridden && (
            <button
              type="button"
              className="btn btn-ghost"
              style={{ fontSize: 11, padding: '0 6px', whiteSpace: 'nowrap' }}
              onClick={() => draft.unsetValue(spec.key)}
            >
              {t.clearOverride}
            </button>
          )}
          {changed && (
            <button
              type="button"
              className="btn btn-ghost"
              style={{ fontSize: 11, padding: '0 6px', whiteSpace: 'nowrap' }}
              onClick={() => draft.revert(spec.key)}
            >
              {t.revert}
            </button>
          )}
        </div>
        {inheriting && (
          <span data-testid="inherit-note" className="text-muted" style={{ fontSize: 11 }}>
            {t.inherit} · {inheritedFrom.label}: {asNote(inheritedFrom.value)}
          </span>
        )}
        {issue && (
          <span id={issueId} role="alert" style={{ fontSize: 11, color: '#a33a2b' }}>
            {issue}
          </span>
        )}
      </div>
    </div>
  )
}
