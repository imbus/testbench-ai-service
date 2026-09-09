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

export function Field({
  spec,
  saved,
  issue,
  lang = 'de',
}: {
  spec: FieldSpec
  /** The value as saved on disk — what an unedited field shows. */
  saved: unknown
  /** A server-side validation message addressed to this field, if any. */
  issue?: string
  lang?: Lang
}) {
  const t = useTranslations(lang)
  const draft = useDraft()
  const value = draft.valueOf(spec.key, saved)
  const changed = draft.isChanged(spec.key)
  const issueId = `${spec.key}-issue`

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
            value={asText(value)}
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
      case 'list':
        return (
          <input
            className="input"
            id={spec.key}
            aria-invalid={issue ? true : undefined}
            aria-describedby={issue ? issueId : undefined}
            value={text ?? asText(value)}
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
            aria-invalid={issue ? true : undefined}
            aria-describedby={issue ? issueId : undefined}
            value={asText(value)}
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
          {spec.key.split('.').pop()}
        </label>
        <span className="text-muted" style={{ fontSize: 11 }}>
          {spec.hint}
        </span>
      </div>
      <div style={{ maxWidth: 480, display: 'flex', flexDirection: 'column', gap: 4 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          {control()}
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
        {issue && (
          <span id={issueId} role="alert" style={{ fontSize: 11, color: '#a33a2b' }}>
            {issue}
          </span>
        )}
      </div>
    </div>
  )
}
