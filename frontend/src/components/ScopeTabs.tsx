import { Dropdown } from 'primereact/dropdown'
import { TabPanel, TabView } from 'primereact/tabview'

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
  // Index 0 is Global; a project's tab sits one past its place in `projects`.
  const scopes: (string | null)[] = [null, ...projects]
  const activeIndex = Math.max(0, scopes.indexOf(selected))

  return (
    <div style={{ display: 'flex', gap: 18, alignItems: 'center', flexWrap: 'wrap' }}>
      {/* Header-only: the scope's fields render below, outside the tab view,
          so every panel is empty and the selection is fully controlled. */}
      <TabView
        activeIndex={activeIndex}
        onTabChange={(event) => onSelect(scopes[event.index] ?? null)}
        style={{ flex: '1 1 auto', minWidth: 0 }}
      >
        <TabPanel header={globalLabel} />
        {projects.map((name) => (
          <TabPanel key={name} header={name} />
        ))}
      </TabView>
      {addable.length > 0 && (
        <Dropdown
          aria-label={addLabel}
          // Always empty: picking a project navigates to its tab, and the
          // placeholder is what invites the next pick.
          value={null}
          placeholder={`+ ${addLabel}`}
          options={addable.map((name) => ({ label: name, value: name }))}
          onChange={(event) => {
            if (event.value) onSelect(event.value)
          }}
          style={{ fontSize: 13 }}
        />
      )}
    </div>
  )
}
