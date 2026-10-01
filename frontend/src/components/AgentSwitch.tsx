import type { ReactNode } from 'react'
import { useTranslations, type Lang } from '../i18n'
import { useDraft } from '../state/draft'

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
  lang = 'de',
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
  lang?: Lang
  /** Row content between the switch and its state caption (the agent's name). */
  children?: ReactNode
}) {
  const t = useTranslations(lang)
  const draft = useDraft()
  const changed = draft.isChanged(path)
  const value = draft.valueOf(path, saved)

  // A queued `null` is a removal, i.e. "inherit again" -- not a value.
  const overridden = value !== null && value !== undefined
  const effective = overridden ? value === true : inherited
  const stateWord = effective ? t.stateOn : t.stateOff
  const caption = overridden ? stateWord : `${t.inherit} (${stateWord})`

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
      <button
        type="button"
        role="switch"
        className="switch"
        aria-checked={effective}
        aria-label={`${label}: ${caption}`}
        title={`${label}: ${caption}`}
        data-state={overridden ? (effective ? 'on' : 'off') : 'inherit'}
        data-changed={String(changed)}
        disabled={readOnly}
        onClick={() => draft.setValue(path, !effective)}
      >
        <span className="switch-knob" />
      </button>
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
        <button
          type="button"
          className="btn btn-ghost"
          style={{ fontSize: 11, padding: '0 6px', whiteSpace: 'nowrap' }}
          onClick={() => draft.unsetValue(path)}
        >
          {t.clearOverride}
        </button>
      )}
    </span>
  )
}
