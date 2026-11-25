import { lastSegment } from '../api/paths'
import { useEffect, useRef, useState } from 'react'
import { Button } from 'primereact/button'
import { Dropdown } from 'primereact/dropdown'
import { InputSwitch } from 'primereact/inputswitch'
import { InputText } from 'primereact/inputtext'
import { InputTextarea } from 'primereact/inputtextarea'
import { Message } from 'primereact/message'
import { useTranslation } from 'react-i18next'
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
}) {
  const { t } = useTranslation()
  const draft = useDraft()
  const draftValue = draft.valueOf(spec.key, saved)
  const changed = draft.isChanged(spec.key)
  // A path is not a DOM id. `aria-labelledby` and `aria-describedby` are
  // space-separated IDREF lists, and a project called `My Project` puts a
  // space in the key -- the switch would then have no accessible name at all
  // and a validation message would never be announced. The draft still keys
  // off `spec.key`; only the DOM sees this.
  const domId = encodeURIComponent(spec.key)
  const issueId = `${domId}-issue`

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

  // What the browser can tell about a number before the server is asked: text
  // that is no number, a number too long to keep exactly, one outside the
  // field's bounds. `badInput` is the one case with nothing to queue -- a
  // number input reports letters as an empty value.
  const [badInput, setBadInput] = useState(false)
  useEffect(() => {
    if (!changed) setBadInput(false)
  }, [changed])
  const numberProblem = (): string | undefined => {
    if (spec.type !== 'number') return undefined
    if (badInput) return t('fieldNumberInvalid')
    if (inheriting || value === null || value === undefined || value === '') return undefined
    if (typeof value === 'string')
      return /^[-+]?\d+$/.test(value.trim()) ? t('fieldNumberTooLarge') : t('fieldNumberInvalid')
    if (typeof value !== 'number') return undefined
    if (spec.min !== undefined && value < spec.min) return t('fieldNumberMin', { min: spec.min })
    if (spec.max !== undefined && value > spec.max) return t('fieldNumberMax', { max: spec.max })
    return undefined
  }
  // The server's issue is about the value it was shown. Once the operator has
  // changed that value -- typed something else, or reverted -- it describes
  // an entry that is no longer there, so it lapses until the next review.
  const valueStamp = JSON.stringify(draftValue ?? null)
  const issueSeen = useRef<{ issue: string | undefined; stamp: string }>({
    issue,
    stamp: valueStamp,
  })
  if (issueSeen.current.issue !== issue) issueSeen.current = { issue, stamp: valueStamp }
  const serverIssue = issue && issueSeen.current.stamp === valueStamp ? issue : undefined
  // The server's word comes first: it has seen the whole configuration.
  const shownIssue = serverIssue ?? numberProblem()

  // Every control reports the issue the same way: Prime's `invalid` for the
  // red border, `aria-invalid`/`aria-describedby` for assistive tech.
  const invalidProps = {
    invalid: shownIssue ? true : undefined,
    'aria-invalid': shownIssue ? true : undefined,
    'aria-describedby': shownIssue ? issueId : undefined,
  }

  const control = () => {
    switch (spec.type) {
      case 'bool':
        return (
          // Prime puts `role="switch"` on the native checkbox inside, which
          // `inputId` makes the label's target; the aria props land there too.
          <InputSwitch
            inputId={domId}
            checked={value === true}
            aria-labelledby={`${domId}-label`}
            {...invalidProps}
            onChange={() => draft.setValue(spec.key, value !== true)}
          />
        )
      case 'select':
        return (
          <Dropdown
            inputId={domId}
            {...invalidProps}
            value={asText(value)}
            // Named explicitly: without `optionValue` Prime treats the blank
            // option's empty value as "no value" and hands back the whole
            // option object instead.
            optionLabel="label"
            optionValue="value"
            options={[
              // The blank option is the way back to no value at all, which is
              // what makes the prompt's own default_variant apply again.
              ...(spec.allowEmpty ? [{ label: '—', value: '' }] : []),
              ...(spec.options ?? []).map((option) => ({ label: option, value: option })),
            ]}
            onChange={(event) =>
              event.value === ''
                ? draft.unsetValue(spec.key)
                : draft.setValue(spec.key, event.value)
            }
            style={{ width: '100%' }}
          />
        )
      case 'number':
        return (
          <InputText
            id={domId}
            type="number"
            {...invalidProps}
            placeholder={placeholder}
            value={inputText}
            min={spec.min}
            max={spec.max}
            onChange={(event) => {
              // Letters in a number input arrive as an empty value: that is not
              // the operator clearing the field, so nothing is queued for it.
              if (event.target.validity?.badInput) {
                setBadInput(true)
                return
              }
              setBadInput(false)
              commit(event.target.value, (text) => {
                const parsed = Number(text)
                // A half-typed "1e" parses to NaN, which JSON.stringify turns
                // into null and the server would read as a removal. Keep the
                // raw text instead and let the server's validation say so.
                if (Number.isNaN(parsed)) return text
                // Past 2^53 a whole number no longer survives the round trip:
                // twenty digits would be written as a different number. The
                // text is kept as typed, and reported, instead.
                if (Number.isInteger(parsed) && !Number.isSafeInteger(parsed)) return text
                return parsed
              })
            }}
            style={{ width: '100%' }}
          />
        )
      case 'textarea':
        return (
          <InputTextarea
            id={domId}
            rows={4}
            {...invalidProps}
            placeholder={placeholder}
            value={inputText}
            onChange={(event) => commit(event.target.value, (text) => text)}
            style={{ width: '100%', fontFamily: 'inherit' }}
          />
        )
      case 'list':
        return (
          <InputText
            id={domId}
            {...invalidProps}
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
            style={{ width: '100%' }}
          />
        )
      default:
        return (
          <InputText
            id={domId}
            type="text"
            {...invalidProps}
            placeholder={placeholder}
            value={inputText}
            onChange={(event) => commit(event.target.value, (text) => text)}
            style={{ width: '100%' }}
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
          id={`${domId}-label`}
          htmlFor={domId}
          // The last segment only, as ReadOnlyField shows it: the section is
          // already in the screen's subheading, so 'llm_config.model' would
          // read as 'llm_config.' twice. The id and htmlFor stay the full
          // dotted key, which is what makes them unique on a screen.
          style={{ fontSize: 13, fontFamily: 'var(--font-code)', display: 'block' }}
        >
          {spec.label ?? lastSegment(spec.key)}
        </label>
        <span className="text-muted" style={{ fontSize: 11 }}>
          {spec.hint}
        </span>
      </div>
      <div
        style={{
          width: '100%',
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
            <Button
              type="button"
              text
              size="small"
              label={t('clearOverride')}
              style={{ whiteSpace: 'nowrap', flex: 'none' }}
              onClick={() => draft.unsetValue(spec.key)}
            />
          )}
          {changed && (
            <Button
              type="button"
              text
              size="small"
              label={t('revert')}
              style={{ whiteSpace: 'nowrap', flex: 'none' }}
              onClick={() => draft.revert(spec.key)}
            />
          )}
        </div>
        {inheriting && (
          <span data-testid="inherit-note" className="text-muted" style={{ fontSize: 11 }}>
            {t('inherit')} · {inheritedFrom.label}: {asNote(inheritedFrom.value)}
          </span>
        )}
        {shownIssue && (
          // `Message` carries role="alert"; the id is what `aria-describedby`
          // on the control points at.
          <Message
            id={issueId}
            severity="error"
            text={shownIssue}
            style={{ alignSelf: 'flex-start' }}
          />
        )}
      </div>
    </div>
  )
}
