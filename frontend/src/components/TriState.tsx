import { useTranslations, type Lang } from '../i18n'
import { useDraft } from '../state/draft'

export type TriStateValue = 'inherit' | 'off' | 'on'

/**
 * A three-state agent toggle: inherit → off → on → inherit (design §5.4).
 *
 * Three states rather than two because a project override in `config.toml` is
 * sparse. A project that says nothing inherits the global setting; a project
 * that says `false` has an opinion. A two-state cell would make "no opinion"
 * unrepresentable, so an override could be set and never removed.
 *
 * Needs no new overlay semantics (design §3.8): "inherit" is the absence of an
 * edit, or a queued `null` when the key is on disk, which the server already
 * reads as "remove the key and fall back".
 */
export function TriState({
  path,
  saved,
  inherited,
  label,
  readOnly = false,
  lang = 'de',
}: {
  /** Edit path this cell writes to — already tokenizer-quoted by the caller. */
  path: string
  /** The override as saved on disk, or `undefined` when there is none. */
  saved: unknown
  /** What applies when this cell inherits — the global agent's `enabled`. */
  inherited: boolean
  /** Names the cell for assistive tech: an icon grid has no other label. */
  label: string
  readOnly?: boolean
  lang?: Lang
}) {
  const t = useTranslations(lang)
  const draft = useDraft()
  const changed = draft.isChanged(path)
  const value = draft.valueOf(path, saved)

  // A queued `null` is a removal, i.e. "inherit again" -- not a value.
  const state: TriStateValue =
    value === null || value === undefined ? 'inherit' : value === true ? 'on' : 'off'

  const effective = state === 'inherit' ? inherited : state === 'on'

  const advance = () => {
    if (state === 'inherit') {
      draft.setValue(path, false)
      return
    }
    if (state === 'off') {
      draft.setValue(path, true)
      return
    }
    // `on` -> inherit. unsetValue writes the removal; when there was nothing on
    // disk to remove the draft prunes it away, so a full cycle leaves no
    // phantom pending change.
    draft.unsetValue(path)
  }

  const stateWord = state === 'inherit' ? t.inherit : state === 'on' ? t.stateOn : t.stateOff
  // The resolved value is part of the label, not only the colour: from the
  // matrix, "inherited" alone would leave the operator unable to tell whether
  // this agent actually runs for this project.
  const spoken =
    state === 'inherit'
      ? `${label}: ${stateWord} (${effective ? t.stateOn : t.stateOff})`
      : `${label}: ${stateWord}`

  const face = state === 'inherit' ? '–' : state === 'on' ? '✓' : '✕'
  const tint =
    state === 'inherit'
      ? 'var(--color-surface)'
      : state === 'on'
        ? 'var(--color-accent-100)'
        : 'var(--color-surface)'

  return (
    <button
      type="button"
      data-state={state}
      data-inherited={String(inherited)}
      data-changed={String(changed)}
      aria-label={spoken}
      title={spoken}
      disabled={readOnly}
      onClick={advance}
      style={{
        width: 30,
        height: 26,
        border: `1px solid ${changed ? 'var(--color-accent)' : 'var(--color-divider)'}`,
        borderRadius: 4,
        background: tint,
        color: 'inherit',
        font: 'inherit',
        fontSize: 13,
        cursor: readOnly ? 'default' : 'pointer',
        // Inheriting cells recede, so a project's own decisions are what
        // stands out in a grid that is mostly inheritance.
        opacity: readOnly ? 0.5 : state === 'inherit' ? 0.55 : 1,
      }}
    >
      {face}
    </button>
  )
}
