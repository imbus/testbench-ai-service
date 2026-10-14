import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Button } from 'primereact/button'
import { Column } from 'primereact/column'
import { DataTable } from 'primereact/datatable'
import { InputSwitch } from 'primereact/inputswitch'
import { Message } from 'primereact/message'
import { Tag } from 'primereact/tag'
import {
  agentKeys,
  agentPath,
  configuredProjects,
  effectiveAgent,
  overridingProjects,
  projectAgentPath,
} from '../api/agents'
import { useConfig, useProjects, usePromptMeta } from '../api/queries'
import { AgentSwitch } from '../components/AgentSwitch'
import { IconToggle, ListIcon, MatrixIcon } from '../components/IconToggle'
import { useTranslation } from 'react-i18next'
import { useDraft } from '../state/draft'
import { valueAt } from './fields'

/**
 * Prime marks the switch's wrapper up as a second, nameless
 * `role="checkbox"` around the real `role="switch"` input; one control
 * should announce once. The same fix `AgentSwitch` applies.
 */
const SWITCH_ROOT = { role: undefined, 'aria-checked': undefined }

/** A mono cell that clips to its column. Paths and endpoints have no break
 *  points, so without this they run on under the next column. */
const MONO_CELL = {
  fontSize: 12,
  fontFamily: 'ui-monospace, Menlo, monospace',
  minWidth: 0,
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
} as const

type View = 'list' | 'matrix'

/**
 * Which agents run, and which projects override them.
 *
 * Two views over the same data: a list, which is where an agent is switched on
 * or off globally and where its detail screen is reached from, and a matrix,
 * which is the only place the whole override picture is visible at once.
 */
export function Agents({ isAdmin }: { isAdmin: boolean }) {
  const { t } = useTranslation()
  const config = useConfig()
  const [view, setView] = useState<View>('list')

  if (config.isLoading) return <div style={{ padding: 28 }}>…</div>
  if (config.isError || !config.data) {
    const detail = (config.error as Error)?.message
    return (
      <div role="alert" style={{ padding: 28 }}>
        <div>{t('configError')}</div>
        {detail && (
          <div className="text-muted" style={{ fontSize: 12, marginTop: 4 }}>
            {detail}
          </div>
        )}
      </div>
    )
  }

  // `?? {}` because `running`/`disk` are whatever the server sent: a payload
  // missing either one must render an empty screen, not crash. An operator who
  // cannot load the console cannot fix the config either.
  const disk = config.data.disk ?? {}
  const running = config.data.running ?? {}
  // Agent keys come from the RUNNING config: the merge validator seeds every
  // built-in, so a config.toml with no [agents] block still has three agents,
  // and reading `disk` alone would show an empty screen for the common case.
  const keys = agentKeys(running)

  return (
    <div
      style={{
        padding: '28px 32px',
        display: 'flex',
        flexDirection: 'column',
        gap: 20,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 30 }}>{t('agents')}</h2>
          <div
            className="text-muted"
            style={{ fontSize: 12, fontFamily: 'ui-monospace, Menlo, monospace' }}
          >
            [testbench-ai-service.agents] · {config.data.config_path}
          </div>
        </div>
        <div style={{ flex: 1 }} />
        {/* Two views of one table, so a segmented control rather than tabs. */}
        <IconToggle
          ariaLabel={t('agents')}
          value={view}
          options={[
            { label: t('viewList'), value: 'list', icon: ListIcon },
            { label: t('viewMatrix'), value: 'matrix', icon: MatrixIcon },
          ]}
          onChange={setView}
        />
      </div>

      {view === 'list' ? (
        <AgentList keys={keys} disk={disk} running={running} isAdmin={isAdmin} />
      ) : (
        <Matrix keys={keys} disk={disk} running={running} isAdmin={isAdmin} />
      )}
    </div>
  )
}

/**
 * The agents as a table: one row per agent, expandable to the projects it is
 * active in.
 */
function AgentList({
  keys,
  disk,
  running,
  isAdmin,
}: {
  keys: string[]
  disk: Record<string, unknown>
  running: Record<string, unknown>
  isAdmin: boolean
}) {
  const { t } = useTranslation()
  const draft = useDraft()
  const projects = useProjects()
  // Keyed by agent, the shape Prime's `expandedRows` takes with a `dataKey`.
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})

  // Every project the agent answers in, not just the ones that say so: an
  // inheriting project runs the agent as surely as an overriding one, and a
  // list of overrides alone reads as "active only here". The same union of
  // TestBench and config the matrix draws its columns from.
  const known = [
    ...new Set([
      ...(projects.data?.projects ?? []).map((entry) => entry.name),
      ...configuredProjects(running),
    ]),
  ]
  const language = String(valueAt(running, 'language') ?? 'de')

  const rows = keys.map((agentKey) => {
    const agent = effectiveAgent(running, agentKey, null)
    const enabledPath = agentPath(agentKey, 'enabled')
    const savedEnabled = valueAt(disk, enabledPath)
    const enabled = draft.valueOf(enabledPath, savedEnabled ?? agent.enabled) === true
    // Resolved through the draft, so a pending switch is reflected before it
    // is applied.
    const perProject = known.map((project) => {
      const path = projectAgentPath(project, agentKey, 'enabled')
      const own = draft.valueOf(path, valueAt(disk, path))
      const overridden = typeof own === 'boolean'
      return { project, overridden, active: overridden ? own : enabled }
    })
    const promptFile = agent.prompt?.file
    return {
      agentKey,
      enabledPath,
      enabled,
      promptFile: typeof promptFile === 'string' ? promptFile : undefined,
      endpoint: typeof agent.endpoint_path === 'string' ? agent.endpoint_path : undefined,
      promptLabel: [agent.prompt?.file, agent.prompt?.variant]
        .filter((part): part is string => typeof part === 'string' && part !== '')
        .join(' · '),
      active: perProject.filter((entry) => entry.active),
      overriders: overridingProjects(running, agentKey),
    }
  })
  type Row = (typeof rows)[number]

  const toggle = (agentKey: string) =>
    setExpanded((current) => {
      const next = { ...current }
      if (next[agentKey]) delete next[agentKey]
      else next[agentKey] = true
      return next
    })

  return (
    <DataTable
      value={rows}
      dataKey="agentKey"
      size="small"
      // Cells read the draft and the expansion state through their closures;
      // Prime's cell memo would keep showing the previous values.
      cellMemo={false}
      expandedRows={expanded}
      rowExpansionTemplate={(row: Row) => (
        <ProjectList agentKey={row.agentKey} active={row.active} />
      )}
      pt={{
        bodyRow: (options) => {
          // Prime passes the row's index in `context` at runtime; its typings
          // only declare `scrollable` there.
          const index = (options?.context as { index?: number } | undefined)?.index
          const row = index === undefined ? undefined : rows[index]
          // Built outside the return, so the `data-*` key passes the type check.
          const props = {
            'data-testid': `agent-row-${row?.agentKey}`,
            // A disabled agent dims as a whole row: the switch alone is a
            // small mark to read across six columns.
            style: { opacity: row?.enabled === false ? 0.6 : 1 },
          }
          return props
        },
      }}
    >
      <Column
        style={{ width: 32 }}
        body={(row: Row) =>
          // Only an expander when there is something to expand. A control
          // that announces itself as collapsible and then opens an empty
          // panel is noise.
          row.active.length === 0 ? (
            <span aria-hidden="true" className="text-muted" style={{ fontSize: 12 }}>
              ·
            </span>
          ) : (
            <Button
              type="button"
              text
              rounded
              size="small"
              aria-expanded={expanded[row.agentKey] === true}
              aria-label={`${t('activeIn')} ${row.active.length} · ${t('overrideCount', { count: row.overriders.length })}`}
              icon={<span style={{ fontSize: 12 }}>{expanded[row.agentKey] ? '▾' : '▸'}</span>}
              onClick={() => toggle(row.agentKey)}
            />
          )
        }
      />
      <Column
        header="Agent"
        body={(row: Row) => (
          <AgentTitle agentKey={row.agentKey} language={language} promptFile={row.promptFile} />
        )}
      />
      <Column
        header={`${t('model')} (${t('effective')})`}
        body={(row: Row) => (
          <AgentModel agentKey={row.agentKey} language={language} promptFile={row.promptFile} />
        )}
      />
      <Column
        header="endpoint_path"
        style={{ maxWidth: 220 }}
        body={(row: Row) => (
          <div className="text-muted" style={MONO_CELL} title={row.endpoint}>
            {row.endpoint ?? '—'}
          </div>
        )}
      />
      <Column
        header="prompt.file · variant"
        style={{ maxWidth: 280 }}
        body={(row: Row) => (
          <div className="text-muted" style={MONO_CELL} title={row.promptLabel || undefined}>
            {row.promptLabel || '—'}
          </div>
        )}
      />
      <Column
        header={t('agentsOn')}
        style={{ width: 190 }}
        body={(row: Row) => (
          <span style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <InputSwitch
              checked={row.enabled}
              disabled={!isAdmin}
              onChange={() => draft.setValue(row.enabledPath, !row.enabled)}
              pt={{
                root: SWITCH_ROOT,
                input: { 'aria-label': `${row.agentKey} ${t('agentsOn')}` },
              }}
            />
            <span className="text-muted" style={{ fontSize: 11, whiteSpace: 'nowrap' }}>
              {t('activeIn')} <span data-testid="active-count">{row.active.length}</span> ·{' '}
              <span data-testid="override-count">{row.overriders.length}</span> {t('overrides')}
            </span>
          </span>
        )}
      />
    </DataTable>
  )
}

/**
 * The agent's name over its key, linked to its detail screen.
 *
 * A component of its own because it reads prompt metadata, and a hook cannot be
 * called inside a column's body template. Metadata is read for the *name*
 * only: a 404 (a prompt file that moved) leaves the row showing its key, which
 * is still the operator's way in to fix the path.
 */
function AgentTitle({
  agentKey,
  language,
  promptFile,
}: {
  agentKey: string
  language: string
  promptFile: string | undefined
}) {
  const meta = usePromptMeta(language, agentKey, promptFile)
  // One link over both lines, as the artboard draws it: the title and the key
  // are the same target, and a reader searching for either finds the row. The
  // key alone when the prompt file is unreadable -- repeating it as its own
  // subtitle says nothing twice.
  return (
    <Link
      to={`/admin/agents/${encodeURIComponent(agentKey)}`}
      style={{ color: 'inherit', minWidth: 0, textDecoration: 'none' }}
    >
      <div style={{ fontFamily: 'var(--font-heading)', fontWeight: 600, fontSize: 16 }}>
        {meta.data?.name ?? agentKey}
      </div>
      {meta.data?.name && (
        <div
          className="text-muted"
          style={{ fontSize: 11, fontFamily: 'ui-monospace, Menlo, monospace' }}
        >
          {agentKey}
        </div>
      )}
    </Link>
  )
}

/** The prompt's default model, from the same cached query `AgentTitle` reads. */
function AgentModel({
  agentKey,
  language,
  promptFile,
}: {
  agentKey: string
  language: string
  promptFile: string | undefined
}) {
  const meta = usePromptMeta(language, agentKey, promptFile)
  return (
    <div className="text-muted" style={MONO_CELL} title={meta.data?.default_model}>
      {meta.data?.default_model ?? '—'}
    </div>
  )
}

/** The expanded row: every project the agent is active in, and why. */
function ProjectList({
  agentKey,
  active,
}: {
  agentKey: string
  active: { project: string; overridden: boolean }[]
}) {
  const { t } = useTranslation()
  return (
    <div
      data-testid={`agent-overrides-${agentKey}`}
      style={{ padding: '4px 0 4px 44px', display: 'flex', flexDirection: 'column', gap: 6 }}
    >
      <div
        className="text-muted"
        style={{ fontSize: 11, letterSpacing: '.08em', textTransform: 'uppercase' }}
      >
        {t('perProject')}
      </div>
      {active.map(({ project, overridden }) => (
        <div
          key={project}
          data-testid={`agent-project-${project}`}
          style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 13 }}
        >
          <span style={{ flex: 1 }}>{project}</span>
          {overridden ? (
            <Tag value={t('override')} style={{ padding: '1px 6px', fontSize: 10 }} />
          ) : (
            <span className="text-muted" style={{ fontSize: 10 }}>
              {t('inherit')}
            </span>
          )}
        </div>
      ))}
    </div>
  )
}

function Matrix({
  keys,
  disk,
  running,
  isAdmin,
}: {
  keys: string[]
  disk: Record<string, unknown>
  running: Record<string, unknown>
  isAdmin: boolean
}) {
  const { t } = useTranslation()
  const projects = useProjects()
  const draft = useDraft()
  // Deduplicated: TestBench has been known to report a name twice, and two
  // columns with the same React key render as one broken column.
  const fromTestBench = [...new Set((projects.data?.projects ?? []).map((entry) => entry.name))]
  const columns = [
    ...fromTestBench,
    ...configuredProjects(running).filter((name) => !fromTestBench.includes(name)),
  ]

  if (columns.length === 0) {
    return (
      <div data-testid="no-projects" className="text-muted" style={{ fontSize: 13 }}>
        {t('noProjects')}
      </div>
    )
  }

  /** What a column header says under the project's name. */
  const columnSub = (project: string): string => {
    const overrides = agentKeys(running).filter(
      (agentKey) => overridingProjects(running, agentKey).indexOf(project) !== -1,
    ).length
    return overrides > 0 ? t('overrideCount', { count: overrides }) : t('inheritsGlobal')
  }

  // Draft-aware, like the list view's own switch: an agent switched off
  // globally in this same unapplied draft must not show every inheriting
  // project as still running it -- the accessible label of each cell states
  // the resolved value, and it would be lying.
  const rows = keys.map((agentKey) => ({
    agentKey,
    inherited:
      draft.valueOf(
        agentPath(agentKey, 'enabled'),
        effectiveAgent(running, agentKey, null).enabled,
      ) === true,
  }))
  type Row = (typeof rows)[number]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {projects.data?.source === 'unavailable' && (
        <Message
          data-testid="projects-unavailable"
          severity="warn"
          text={t('projectsUnavailable')}
          style={{ alignSelf: 'flex-start', fontSize: 12 }}
        />
      )}
      <DataTable
        value={rows}
        dataKey="agentKey"
        size="small"
        showGridlines
        scrollable
        // The switches read the draft through their closures; Prime's cell
        // memo would keep showing the previous values.
        cellMemo={false}
        style={{ fontSize: 13 }}
      >
        <Column
          field="agentKey"
          style={{ minWidth: 220, whiteSpace: 'nowrap' }}
          // The agent's cell names the row, as a `<th scope="row">` would.
          pt={{ bodyCell: { role: 'rowheader' } }}
          body={(row: Row) => (
            <span style={{ fontFamily: 'ui-monospace, Menlo, monospace' }}>{row.agentKey}</span>
          )}
        />
        {columns.map((project) => {
          const inTestBench = fromTestBench.includes(project)
          // Built outside the `pt` literal, so the `data-*` keys pass the
          // type check.
          const headerCell = {
            'data-testid': `column-${project}`,
            'data-in-testbench': String(inTestBench),
            title: inTestBench ? project : `${project} · ${t('notInTestBench')}`,
          }
          return (
            <Column
              key={project}
              style={{ minWidth: 150, verticalAlign: 'bottom', whiteSpace: 'nowrap' }}
              // The tint fills the whole cell, so the padding moves inside it.
              bodyStyle={{ padding: 0 }}
              pt={{ headerCell }}
              header={
                <div>
                  <div
                    style={{
                      fontFamily: 'var(--font-heading)',
                      fontSize: 15,
                      fontWeight: 400,
                      color: inTestBench ? 'inherit' : '#a33a2b',
                    }}
                  >
                    {project}
                    {!inTestBench && ' ⚠'}
                  </div>
                  <div className="text-muted" style={{ fontSize: 11, fontWeight: 400 }}>
                    {columnSub(project)}
                  </div>
                </div>
              }
              body={(row: Row) => {
                const path = projectAgentPath(project, row.agentKey, 'enabled')
                // The cell that carries an opinion is tinted, so the shape of
                // the overrides is readable across the whole grid before any
                // single cell is read.
                const own = draft.valueOf(path, valueAt(disk, path))
                const overridden = own !== undefined && own !== null
                return (
                  <div
                    style={{
                      padding: '4px 12px',
                      background: overridden ? 'var(--color-accent-100)' : 'transparent',
                    }}
                  >
                    <AgentSwitch
                      path={path}
                      saved={valueAt(disk, path)}
                      inherited={row.inherited}
                      label={`${row.agentKey} · ${project}`}
                      readOnly={!isAdmin}
                    />
                  </div>
                )
              }}
            />
          )
        })}
      </DataTable>
    </div>
  )
}
