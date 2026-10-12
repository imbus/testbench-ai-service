import type { ReactNode } from 'react'
import { Button } from 'primereact/button'
import { InputSwitch } from 'primereact/inputswitch'
import { useTranslation } from 'react-i18next'
import { useDraft } from '../state/draft'

/**
 * Prime marks the switch's wrapper up as a second, nameless
 * `role="checkbox"` around the real `role="switch"` input; one control
 * should announce once.
 */
const SWITCH_ROOT = { role: undefined, 'aria-checked': undefined }

/**
 * An on/off switch for one agent in one project, plus a way back to inherit.
 *
 * The switch shows what actually applies: the project's override when it has
 * one, the global agent's `enabled` otherwise. Flipping it always writes an
 * explicit override. A project override in `config.toml` is sparse -- a project
 * that says nothing inherits -- so two states alone would make "no opinion"
 * unreachable once an override is set. While one exists a "Clear override"
 * button sits beside the switch and queues its removal.
 */
export function AgentSwitch({
  path,
  saved,
  inherited,
  label,
  readOnly = false,
  children,
}: {
  /** Edit path this switch writes to — already tokenizer-quoted by the caller. */
  path: string
  /** The override as saved on disk, or `undefined` when there is none. */
  saved: unknown
  /** What applies while inheriting — the global agent's `enabled`. */
  inherited: boolean
  /** Names the switch for assistive tech. */
  label: string
  readOnly?: boolean
  /** Row content between the switch and its state caption (the agent's name). */
  children?: ReactNode
}) {
  const { t } = useTranslation()
  const draft = useDraft()
  const changed = draft.isChanged(path)
  const value = draft.valueOf(path, saved)

  // A queued `null` is a removal, i.e. "inherit again" -- not a value.
  const overridden = value !== null && value !== undefined
  const effective = overridden ? value === true : inherited
  const stateWord = effective ? t('stateOn') : t('stateOff')
  const caption = overridden ? stateWord : `${t('inherit')} (${stateWord})`

  // The name, the state and the draft markers go on Prime's inner
  // `role="switch"` input -- the element assistive tech and the tests reach.
  // Built outside the `pt` literal, so the `data-*` keys pass the type check.
  const switchInput = {
    'aria-label': `${label}: ${caption}`,
    'data-state': overridden ? (effective ? 'on' : 'off') : 'inherit',
    'data-changed': String(changed),
  }

  return (
    <span
      className="switch-row"
      style={{
        minHeight: 0,
        flex: 1,
        minWidth: 0,
        gap: '4px 10px',
        flexWrap: 'wrap',
      }}
    >
      <InputSwitch
        checked={effective}
        title={`${label}: ${caption}`}
        disabled={readOnly}
        onChange={() => draft.setValue(path, !effective)}
        pt={{ root: SWITCH_ROOT, input: switchInput }}
      />
      {children}
      <span
        className="switch-caption"
        aria-hidden="true"
        style={{
          fontSize: 12,
          whiteSpace: 'nowrap',
          opacity: overridden ? 1 : 0.7,
        }}
      >
        {caption}
      </span>
      {overridden && !readOnly && (
        <Button
          type="button"
          text
          size="small"
          label={t('clearOverride')}
          style={{ fontSize: 11, padding: '0 6px', whiteSpace: 'nowrap' }}
          onClick={() => draft.unsetValue(path)}
        />
      )}
    </span>
  )
}
