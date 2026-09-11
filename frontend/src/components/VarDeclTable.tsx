import { useState } from 'react'

import type { PromptVarDecl, VarValueType } from '../api/types'

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
 * drift from its own `choices`.
 */
function DefaultValueControl({
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
      <button
        type="button"
        role="switch"
        id={id}
        aria-checked={checked}
        aria-labelledby={labelId}
        disabled={readOnly}
        className="btn btn-ghost"
        onClick={() => onChange(!checked)}
      >
        {checked ? 'true' : 'false'}
      </button>
    )
  }

  if (decl.value_type === 'number') {
    return (
      <input
        className="input"
        id={id}
        type="number"
        aria-labelledby={labelId}
        disabled={readOnly}
        value={typeof value === 'number' ? value : ''}
        onChange={(event) => {
          const raw = event.target.value
          if (raw.trim() === '') {
            onChange(null)
            return
          }
          const parsed = Number(raw)
          onChange(Number.isNaN(parsed) ? raw : parsed)
        }}
      />
    )
  }

  if (decl.value_type === 'text') {
    return (
      <textarea
        className="input"
        id={id}
        aria-labelledby={labelId}
        disabled={readOnly}
        value={typeof value === 'string' ? value : ''}
        onChange={(event) => onChange(event.target.value || null)}
      />
    )
  }

  if (decl.value_type === 'enum') {
    const choices = decl.choices ?? []
    return (
      <select
        className="input"
        id={id}
        aria-labelledby={labelId}
        disabled={readOnly}
        value={typeof value === 'string' ? value : ''}
        onChange={(event) => onChange(event.target.value || null)}
      >
        <option value="">—</option>
        {choices.map((choice) => (
          <option key={choice} value={choice}>
            {choice}
          </option>
        ))}
      </select>
    )
  }

  return (
    <input
      className="input"
      id={id}
      type="text"
      aria-labelledby={labelId}
      disabled={readOnly}
      value={typeof value === 'string' ? value : ''}
      onChange={(event) => onChange(event.target.value || null)}
    />
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
    <div
      data-testid="var-row"
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 6,
        padding: '10px 0',
        borderBottom: '1px solid var(--color-divider)',
      }}
    >
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'center' }}>
        <input
          className="input"
          aria-label="Name"
          value={name}
          readOnly
          style={{ width: 140, fontFamily: 'ui-monospace, Menlo, monospace' }}
        />
        <div style={{ display: 'flex', flexDirection: 'column', flex: 1, minWidth: 160 }}>
          <label htmlFor={descriptionId} style={{ fontSize: 11 }}>
            Description
          </label>
          <input
            className="input"
            id={descriptionId}
            disabled={readOnly}
            value={decl.description ?? ''}
            onChange={(event) => onEdit({ ...decl, description: event.target.value || null })}
          />
        </div>
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          <label htmlFor={typeId} style={{ fontSize: 11 }}>
            Type
          </label>
          <select
            className="input"
            id={typeId}
            disabled={readOnly}
            value={decl.value_type}
            onChange={(event) => {
              const value_type = event.target.value as VarValueType
              onEdit({
                ...decl,
                value_type,
                // Mirrors the reducer's own edge handling: choices only ever
                // makes sense on the enum side.
                choices: value_type === 'enum' ? (decl.choices ?? []) : null,
              })
            }}
          >
            {VALUE_TYPES.map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </select>
        </div>
        {decl.value_type === 'enum' && (
          <div style={{ display: 'flex', flexDirection: 'column', minWidth: 160 }}>
            <label htmlFor={choicesId} style={{ fontSize: 11 }}>
              Choices
            </label>
            <input
              className="input"
              id={choicesId}
              placeholder="a, b, c"
              disabled={readOnly}
              value={(decl.choices ?? []).join(', ')}
              onChange={(event) => onEdit({ ...decl, choices: parseChoices(event.target.value) })}
            />
          </div>
        )}
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          <span id={defaultLabelId} style={{ fontSize: 11 }}>
            Default value
          </span>
          <DefaultValueControl
            id={defaultId}
            labelId={defaultLabelId}
            decl={decl}
            readOnly={readOnly}
            onChange={(value) => onEdit({ ...decl, default_value: value })}
          />
        </div>
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          <span id={requiredLabelId} style={{ fontSize: 11 }}>
            Required
          </span>
          <button
            type="button"
            role="switch"
            aria-checked={decl.required}
            aria-labelledby={requiredLabelId}
            disabled={readOnly}
            className="btn btn-ghost"
            onClick={() => onEdit({ ...decl, required: !decl.required })}
          >
            {decl.required ? 'required' : 'optional'}
          </button>
        </div>
        {!readOnly && (
          <button type="button" className="btn btn-ghost" onClick={onRemove}>
            Remove
          </button>
        )}
      </div>
      {invalidEnum && (
        <span role="alert" style={{ fontSize: 11, color: '#a33a2b' }}>
          An enum variable needs at least one entry in choices.
        </span>
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
  const [pending, setPending] = useState('')

  return (
    <div>
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
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', paddingTop: 10 }}>
          <input
            className="input"
            aria-label="New variable name"
            placeholder="New variable name"
            value={pending}
            onChange={(event) => setPending(event.target.value)}
          />
          <button
            type="button"
            className="btn btn-ghost"
            onClick={() => {
              const key = pending.trim()
              if (!key) return
              onAdd(key)
              setPending('')
            }}
          >
            Add
          </button>
        </div>
      )}
    </div>
  )
}
