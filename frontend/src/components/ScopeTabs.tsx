/**
 * The Global / per-project scope switcher.
 *
 * Shared by the Agents screen and the LLM screen so there is one answer to
 * "edit this globally or per project" rather than two that drift apart.
 *
 * Choosing a scope is navigation, never an edit: this component reports the
 * choice and holds no draft state. Writing an empty override table on
 * selection would put a change in the operator's diff they never asked for.
 */
export function ScopeTabs({
  projects,
  selected,
  addable,
  onSelect,
  globalLabel,
  addLabel,
}: {
  /** Project tabs to show, in order. */
  projects: string[]
  /** The current scope; `null` is the Global tab. */
  selected: string | null
  /** Projects offered by the add select — those without a tab. */
  addable: string[]
  onSelect: (project: string | null) => void
  /** Already translated by the caller: this component holds no dictionary. */
  globalLabel: string
  addLabel: string
}) {
  return (
    <div
      role="tablist"
      style={{ display: 'flex', gap: 18, alignItems: 'center', flexWrap: 'wrap' }}
    >
      <ScopeTab label={globalLabel} selected={selected === null} onSelect={() => onSelect(null)} />
      {projects.map((name) => (
        <ScopeTab
          key={name}
          label={name}
          selected={selected === name}
          onSelect={() => onSelect(name)}
        />
      ))}
      {addable.length > 0 && (
        <select
          className="input"
          aria-label={addLabel}
          value=""
          style={{ fontSize: 13, width: 'auto' }}
          onChange={(event) => {
            if (event.target.value) onSelect(event.target.value)
          }}
        >
          <option value="">+ {addLabel}</option>
          {addable.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
      )}
    </div>
  )
}

function ScopeTab({
  label,
  selected,
  onSelect,
}: {
  label: string
  selected: boolean
  onSelect: () => void
}) {
  return (
    <button
      type="button"
      role="tab"
      className="tb-chip"
      aria-selected={selected}
      onClick={onSelect}
      style={{
        // A chip, as the artboard draws the scope switcher -- but still a tab,
        // because that is what selecting a scope is.
        border: '1px solid var(--color-divider)',
        padding: '4px 12px',
        font: 'inherit',
        fontSize: 13,
        background: selected ? 'var(--color-accent)' : 'transparent',
        color: selected ? 'var(--color-bg)' : 'inherit',
        cursor: 'pointer',
      }}
    >
      {label}
    </button>
  )
}
