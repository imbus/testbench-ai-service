import { useState } from 'react'
import { Button } from 'primereact/button'
import { Dropdown } from 'primereact/dropdown'
import { InputSwitch } from 'primereact/inputswitch'
import { InputText } from 'primereact/inputtext'
import { InputTextarea } from 'primereact/inputtextarea'
import { Message } from 'primereact/message'
import { useTranslation } from 'react-i18next'
import type { PromptVarDecl, VarValueType } from '../api/types'

// Wire tokens round-tripped through the API, not prose -- kept in English
// regardless of the UI language, matching how Field.tsx never translates `spec.key`.
const VALUE_TYPES: VarValueType[] = ['string', 'text', 'boolean', 'number', 'enum']

/** Comma-separated choices as typed, trimmed and stripped of blanks. */
function parseChoices(raw: string): string[] {
  return raw
    .split(',')
    .map((entry) => entry.trim())
    .filter((entry) => entry !== '')
}

/**
 * `default_value` typed by the declared `value_type`.
 *
 * Kept as one control per type (rather than always a text box) so a boolean
 * default can't be typed as the string "false" and an enum default can't
 * drift from its own `choices`. The boolean face reads literal `true`/`false`
 * -- it represents the serialized value, not an on/off UI state -- so it
 * isn't translated either.
 *
 * Also the render preview's sample-value control: it reads `default_value`,
 * so the preview hands it a decl carrying the operator's sample instead.
 */
export function DefaultValueControl({
  id,
  labelId,
  decl,
  readOnly,
  onChange,
}: {
  id: string
  labelId: string
  decl: PromptVarDecl
  readOnly?: boolean
  onChange: (value: unknown) => void
}) {
  const value = decl.default_value

  if (decl.value_type === 'boolean') {
    const checked = value === true
    return (
      <Switch
        id={id}
        labelId={labelId}
        checked={checked}
        disabled={readOnly}
        caption={checked ? 'true' : 'false'}
        onToggle={() => onChange(!checked)}
      />
    )
  }

  if (decl.value_type === 'number') {
    return (
      <InputText
        id={id}
        type="number"
        aria-labelledby={labelId}
        disabled={readOnly}
        value={typeof value === 'number' ? String(value) : ''}
        onChange={(event) => {
          const raw = event.target.value
          if (raw.trim() === '') {
            onChange(null)
            return
          }
          const parsed = Number(raw)
          onChange(Number.isNaN(parsed) ? raw : parsed)
        }}
        style={{ width: '100%' }}
      />
    )
  }

  if (decl.value_type === 'text') {
    return (
      <InputTextarea
        id={id}
        aria-labelledby={labelId}
        disabled={readOnly}
        value={typeof value === 'string' ? value : ''}
        onChange={(event) => onChange(event.target.value || null)}
        style={{ width: '100%', fontFamily: 'inherit' }}
      />
    )
  }

  if (decl.value_type === 'enum') {
    const choices = decl.choices ?? []
    return (
      <Dropdown
        inputId={id}
        aria-labelledby={labelId}
        disabled={readOnly}
        value={typeof value === 'string' ? value : ''}
        // Named explicitly, as in Field.tsx: without `optionValue` Prime
        // treats the blank option's empty value as "no value" and hands back
        // the whole option object instead.
        optionLabel="label"
        optionValue="value"
        options={[
          { label: '—', value: '' },
          ...choices.map((choice) => ({ label: choice, value: choice })),
        ]}
        onChange={(event) => onChange(event.value || null)}
        style={{ width: '100%' }}
      />
    )
  }

  return (
    <InputText
      id={id}
      type="text"
      aria-labelledby={labelId}
      disabled={readOnly}
      value={typeof value === 'string' ? value : ''}
      onChange={(event) => onChange(event.target.value || null)}
      style={{ width: '100%' }}
    />
  )
}

/**
 * An on/off switch, the same `InputSwitch` as Field.tsx's bool control; the
 * caption sits beside the track so the state reads in words as well as
 * position.
 */
function Switch({
  id,
  labelId,
  checked,
  disabled,
  caption,
  onToggle,
}: {
  id?: string
  labelId: string
  checked: boolean
  disabled?: boolean
  caption: string
  onToggle: () => void
}) {
  return (
    <span className="switch-row">
      {/* Prime puts `role="switch"` on the native checkbox inside, which
          `inputId` makes the label's target; the aria props land there too. */}
      <InputSwitch
        inputId={id}
        checked={checked}
        aria-labelledby={labelId}
        disabled={disabled}
        onChange={onToggle}
      />
      <span className="switch-caption" aria-hidden="true">
        {caption}
      </span>
    </span>
  )
}

function VarRow({
  name,
  decl,
  readOnly,
  onEdit,
  onRemove,
}: {
  name: string
  decl: PromptVarDecl
  readOnly?: boolean
  onEdit: (decl: PromptVarDecl) => void
  onRemove: () => void
}) {
  const { t } = useTranslation()

  // A path is not a DOM id (mirrors Field.tsx's own note on the same hazard);
  // a variable name is a plain identifier in practice, but this keeps every
  // id well-formed regardless.
  const rowId = encodeURIComponent(name)
  const typeId = `${rowId}-type`
  const descriptionId = `${rowId}-description`
  const choicesId = `${rowId}-choices`
  const defaultId = `${rowId}-default`
  const defaultLabelId = `${defaultId}-label`
  const requiredLabelId = `${rowId}-required-label`

  // PromptVariableDefinition.validate_choices requires a non-empty `choices`
  // on an enum. The reducer normalises an absent/null value to `[]` so this
  // can render the control and catch the empty case before a save 422s.
  const invalidEnum = decl.value_type === 'enum' && (decl.choices ?? []).length === 0

  return (
    <div data-testid="var-row" className="var-card">
      <div className="var-card-head">
        <code className="var-card-name">
          {`{{ ${name} }}`}
        </code>
        <span className="var-card-required">
          <span id={requiredLabelId}>{t('varRequired')}</span>
          <Switch
            labelId={requiredLabelId}
            checked={decl.required}
            disabled={readOnly}
            caption={decl.required ? t('varRequiredOn') : t('varRequiredOff')}
            onToggle={() => onEdit({ ...decl, required: !decl.required })}
          />
        </span>
        {!readOnly && (
          <Button type="button" text label={t('remove')} onClick={onRemove} />
        )}
      </div>
      <div className="var-card-grid">
        <div className="field var-card-wide">
          <label htmlFor={descriptionId}>{t('varDescription')}</label>
          <InputText
            id={descriptionId}
            disabled={readOnly}
            value={decl.description ?? ''}
            onChange={(event) => onEdit({ ...decl, description: event.target.value || null })}
            style={{ width: '100%' }}
          />
        </div>
        <div className="field">
          <label htmlFor={typeId}>{t('varType')}</label>
          <Dropdown
            inputId={typeId}
            disabled={readOnly}
            value={decl.value_type}
            options={VALUE_TYPES.map((type) => ({ label: type, value: type }))}
            onChange={(event) => {
              const value_type = event.value as VarValueType
              onEdit({
                ...decl,
                value_type,
                // Mirrors the reducer's own edge handling: choices only ever
                // makes sense on the enum side.
                choices: value_type === 'enum' ? (decl.choices ?? []) : null,
              })
            }}
            style={{ width: '100%' }}
          />
        </div>
        {decl.value_type === 'enum' && (
          <div className="field">
            <label htmlFor={choicesId}>{t('varChoices')}</label>
            <InputText
              id={choicesId}
              placeholder={t('varChoicesPlaceholder')}
              disabled={readOnly}
              invalid={invalidEnum || undefined}
              aria-invalid={invalidEnum || undefined}
              value={(decl.choices ?? []).join(', ')}
              onChange={(event) => onEdit({ ...decl, choices: parseChoices(event.target.value) })}
              style={{ width: '100%' }}
            />
          </div>
        )}
        <div className={decl.value_type === 'text' ? 'field var-card-wide' : 'field'}>
          <label id={defaultLabelId} htmlFor={defaultId}>
            {t('varDefaultValue')}
          </label>
          <DefaultValueControl
            id={defaultId}
            labelId={defaultLabelId}
            decl={decl}
            readOnly={readOnly}
            onChange={(value) => onEdit({ ...decl, default_value: value })}
          />
        </div>
      </div>
      {invalidEnum && (
        // `Message` carries role="alert".
        <Message
          severity="error"
          text={t('varEnumNeedsChoices')}
          style={{ alignSelf: 'flex-start' }}
        />
      )}
    </div>
  )
}

export function VarDeclTable({
  vars,
  readOnly,
  onAdd,
  onEdit,
  onRemove,
}: {
  vars: Record<string, PromptVarDecl>
  readOnly?: boolean
  onAdd: (key: string) => void
  onEdit: (key: string, decl: PromptVarDecl) => void
  onRemove: (key: string) => void
}) {
  const { t } = useTranslation()
  const [pending, setPending] = useState('')

  return (
    <div className="var-list">
      {Object.entries(vars).map(([name, decl]) => (
        <VarRow
          key={name}
          name={name}
          decl={decl}
          readOnly={readOnly}
          onEdit={(next) => onEdit(name, next)}
          onRemove={() => onRemove(name)}
        />
      ))}
      {!readOnly && (
        <form
          className="var-add"
          onSubmit={(event) => {
            event.preventDefault()
            const key = pending.trim()
            if (!key) return
            onAdd(key)
            setPending('')
          }}
        >
          <InputText
            aria-label={t('varNewName')}
            placeholder={t('varNewName')}
            value={pending}
            onChange={(event) => setPending(event.target.value)}
            style={{ flex: 1, minWidth: 0 }}
          />
          <Button type="submit" outlined label={t('add')} disabled={!pending.trim()} />
        </form>
      )}
    </div>
  )
}
