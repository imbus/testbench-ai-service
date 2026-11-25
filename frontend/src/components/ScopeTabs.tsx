import { useRef, useState } from 'react'
import { TabPanel, TabView } from 'primereact/tabview'
import { SearchPopover } from './SearchPopover'

/** Texts of the "+" picker, already translated by the caller. */
export interface ScopeAddLabels {
  /** Names the "+" button (tooltip, `aria-label`) and the picker. */
  button: string
  /** Placeholder and label of the search field. */
  search: string
  /** Shown when the search matches no project. */
  noMatch: string
  /** Footer line: picking only navigates, nothing is written yet. */
  hint: string
}

/** The picker texts from the console dictionary, for both screens that use the tabs. */
export function scopeAddLabels(
  t: (
    key:
      | 'addProjectOverride'
      | 'scopeSearch'
      | 'scopeNoMatch'
      | 'scopePickHint'
      | 'scopePickHintReadOnly',
  ) => string,
  /** A viewer who cannot change anything is not told about saving. */
  readOnly = false,
): ScopeAddLabels {
  return {
    button: t('addProjectOverride'),
    search: t('scopeSearch'),
    noMatch: t('scopeNoMatch'),
    hint: t(readOnly ? 'scopePickHintReadOnly' : 'scopePickHint'),
  }
}

/** Same edge as a Prime tab link, so the strip's line runs on past the tabs. */
const TAB_LINE = '2px solid var(--color-divider)'

/**
 * The Global / per-project scope switcher.
 *
 * Shared by the Agents screen and the LLM screen so there is one answer to
 * "edit this globally or per project" rather than two that drift apart.
 *
 * Choosing a scope is navigation, never an edit: this component reports the
 * choice and holds no draft state. Writing an empty override table on
 * selection would put a change in the operator's diff they never asked for.
 * That is also why the way to a project without a tab is a "+" tab, not a
 * form field: it reads as one more place to go, not as something to fill in.
 */
export function ScopeTabs({
  projects,
  selected,
  addable,
  onSelect,
  globalLabel,
  addLabels,
}: {
  /** Project tabs to show, in order. */
  projects: string[]
  /** The current scope; `null` is the Global tab. */
  selected: string | null
  /** Projects offered by the "+" picker; those that have a tab are left out. */
  addable: string[]
  onSelect: (project: string | null) => void
  /** Already translated by the caller: this component holds no dictionary. */
  globalLabel: string
  addLabels: ScopeAddLabels
}) {
  // Index 0 is Global; a project's tab sits one past its place in `projects`.
  const scopes: (string | null)[] = [null, ...projects]
  const activeIndex = Math.max(0, scopes.indexOf(selected))
  const offered = addable.filter((name) => !projects.includes(name))

  return (
    <div style={{ display: 'flex', alignItems: 'flex-end', minWidth: 0 }}>
      {/* Header-only: the scope's fields render below, outside the tab view,
          so every panel is empty and the selection is fully controlled. */}
      <TabView
        activeIndex={activeIndex}
        onTabChange={(event) => onSelect(scopes[event.index] ?? null)}
        style={{ flex: '0 1 auto', minWidth: 0 }}
      >
        <TabPanel header={globalLabel} />
        {projects.map((name) => (
          <TabPanel key={name} header={name} />
        ))}
      </TabView>
      {offered.length > 0 && <AddScope projects={offered} labels={addLabels} onPick={onSelect} />}
      <div aria-hidden style={{ flex: '1 1 auto', alignSelf: 'stretch', borderBottom: TAB_LINE }} />
    </div>
  )
}

/** The "+" tab and its searchable project list. */
function AddScope({
  projects,
  labels,
  onPick,
}: {
  projects: string[]
  labels: ScopeAddLabels
  onPick: (project: string) => void
}) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const root = useRef<HTMLDivElement>(null)
  const button = useRef<HTMLButtonElement>(null)

  const needle = query.trim().toLocaleLowerCase()
  const matches = projects.filter((name) => name.toLocaleLowerCase().includes(needle))

  const close = (refocus: boolean) => {
    setOpen(false)
    setQuery('')
    if (refocus) button.current?.focus()
  }
  const pick = (name: string) => {
    close(false)
    onPick(name)
  }

  return (
    <div ref={root} style={{ position: 'relative', flex: 'none' }}>
      <button
        ref={button}
        type="button"
        className="scope-add"
        aria-label={labels.button}
        title={labels.button}
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => (open ? close(false) : setOpen(true))}
        style={{
          font: 'inherit',
          fontSize: 18,
          lineHeight: '21px',
          fontWeight: 600,
          padding: '8px 14px',
          cursor: 'pointer',
          color: 'var(--color-accent-fg)',
          background: open
            ? 'color-mix(in srgb, var(--color-accent) 10%, transparent)'
            : 'transparent',
          border: 0,
          borderBottom: TAB_LINE,
        }}
      >
        +
      </button>
      {open && (
        <SearchPopover
          anchor={root}
          onDismiss={() => close(false)}
          label={labels.button}
          searchLabel={labels.search}
          query={query}
          onQuery={setQuery}
          onEnter={() => matches.length > 0 && pick(matches[0])}
          onEscape={() => close(true)}
          footer={labels.hint}
        >
          {matches.map((name) => (
            <li key={name}>
              <button type="button" className="tb-popover-item" onClick={() => pick(name)}>
                {name}
              </button>
            </li>
          ))}
          {matches.length === 0 && <li className="tb-popover-empty">{labels.noMatch}</li>}
        </SearchPopover>
      )}
    </div>
  )
}
