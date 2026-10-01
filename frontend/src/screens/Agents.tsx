import { useState } from 'react'
import { Link } from 'react-router-dom'
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
import { useTranslations, type Lang } from '../i18n'
import { useDraft } from '../state/draft'
import { valueAt } from './fields'

/** The list's column track. The header strip and every row share it, or
 *  the columns stop lining up the moment one of them is edited. */
const GRID_COLUMNS =
  '32px minmax(0, 1.4fr) minmax(0, 0.7fr) minmax(0, 1fr) minmax(0, 1.4fr) 190px'

/** A mono cell that clips to its track. Paths and endpoints have no break
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
export function Agents({ lang, isAdmin }: { lang: Lang; isAdmin: boolean }) {
  const t = useTranslations(lang)
  const config = useConfig()
  const [view, setView] = useState<View>('list')

  if (config.isLoading) return <div style={{ padding: 28 }}>…</div>
  if (config.isError || !config.data) {
    const detail = (config.error as Error)?.message
    return (
      <div role="alert" style={{ padding: 28 }}>
        <div>{t.configError}</div>
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
          <h2 style={{ margin: 0, fontSize: 30 }}>{t.agents}</h2>
          <div
            className="text-muted"
            style={{ fontSize: 12, fontFamily: 'ui-monospace, Menlo, monospace' }}
          >
            [testbench-ai-service.agents] · {config.data.config_path}
          </div>
        </div>
        <div style={{ flex: 1 }} />
        {/* Two views of one table, so a segmented control rather than tabs:
            the design system paints the checked option through
            `.seg:has(input:checked)`, which needs real radios. */}
        <div className="seg" role="radiogroup" aria-label={t.agents}>
          {(['list', 'matrix'] as const).map((entry) => (
            <label key={entry} className="seg-opt">
              <input
                type="radio"
                name="agents-view"
                checked={view === entry}
                onChange={() => setView(entry)}
              />
              {entry === 'list' ? t.viewList : t.viewMatrix}
            </label>
          ))}
        </div>
      </div>

      {view === 'list' ? (
        <div className="blueprint" style={{ overflowX: 'auto' }}>
          <i className="corner tl" />
          <i className="corner tr" />
          <i className="corner bl" />
          <i className="corner br" />
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: GRID_COLUMNS,
              gap: 12,
              padding: '8px 14px',
              borderBottom: '1px solid var(--color-divider)',
              fontSize: 11,
              letterSpacing: '.08em',
              textTransform: 'uppercase',
              color: 'color-mix(in srgb, var(--color-text) 60%, transparent)',
            }}
          >
            <span />
            <span>Agent</span>
            <span>
              {t.model} ({t.effective})
            </span>
            <span>endpoint_path</span>
            <span>prompt.file · variant</span>
            <span>{t.agentsOn}</span>
          </div>
          {keys.map((key) => (
            <AgentRow
              key={key}
              agentKey={key}
              disk={disk}
              running={running}
              lang={lang}
              isAdmin={isAdmin}
            />
          ))}
        </div>
      ) : (
        <Matrix keys={keys} disk={disk} running={running} lang={lang} isAdmin={isAdmin} />
      )}
    </div>
  )
}

/**
 * One agent in the list view.
 *
 * A component of its own because it reads prompt metadata, and a hook cannot be
 * called in a loop inside the parent.
 */
function AgentRow({
  agentKey,
  disk,
  running,
  lang,
  isAdmin,
}: {
  agentKey: string
  disk: Record<string, unknown>
  running: Record<string, unknown>
  lang: Lang
  isAdmin: boolean
}) {
  const t = useTranslations(lang)
  const draft = useDraft()
  const [expanded, setExpanded] = useState(false)

  const agent = effectiveAgent(running, agentKey, null)
  const language = String(valueAt(running, 'language') ?? 'de')
  const promptFile = agent.prompt?.file
  // Metadata is read for the agent's *name* only here. A 404 (a prompt file
  // that moved) leaves the row showing its key, which is still the operator's
  // way in to fix the path.
  const meta = usePromptMeta(language, agentKey, typeof promptFile === 'string' ? promptFile : undefined)

  const projects = useProjects()
  const overriders = overridingProjects(running, agentKey)
  const enabledPath = agentPath(agentKey, 'enabled')
  const savedEnabled = valueAt(disk, enabledPath)
  const enabled = draft.valueOf(enabledPath, savedEnabled ?? agent.enabled) === true

  // Every project the agent answers in, not just the ones that say so: an
  // inheriting project runs the agent as surely as an overriding one, and a
  // list of overrides alone reads as "active only here". The same union of
  // TestBench and config the matrix draws its columns from, resolved through
  // the draft so a pending switch is reflected before it is applied.
  const known = [
    ...new Set([
      ...(projects.data?.projects ?? []).map((entry) => entry.name),
      ...configuredProjects(running),
    ]),
  ]
  const perProject = known.map((project) => {
    const path = projectAgentPath(project, agentKey, 'enabled')
    const own = draft.valueOf(path, valueAt(disk, path))
    const overridden = typeof own === 'boolean'
    return { project, overridden, active: overridden ? own : enabled }
  })
  const active = perProject.filter((entry) => entry.active)

  const promptLabel = [agent.prompt?.file, agent.prompt?.variant]
    .filter((part): part is string => typeof part === 'string' && part !== '')
    .join(' · ')

  return (
    <div data-testid={`agent-row-${agentKey}`}>
      <div
        className="tb-row"
        style={{
          display: 'grid',
          gridTemplateColumns: GRID_COLUMNS,
          gap: 12,
          alignItems: 'center',
          padding: '8px 14px',
          borderBottom: '1px solid var(--color-divider)',
          // A disabled agent dims as a whole row: the switch alone is a small
          // mark to read across six columns.
          opacity: enabled ? 1 : 0.6,
        }}
      >
        {/* Only an expander when there is something to expand. A control
            that announces itself as collapsible and then opens an empty
            panel is noise. */}
        {active.length === 0 ? (
          <span aria-hidden="true" className="text-muted" style={{ fontSize: 12 }}>
            ·
          </span>
        ) : (
          <button
            type="button"
            aria-expanded={expanded}
            aria-label={`${t.activeIn} ${active.length} · ${overriders.length} ${t.overrides}`}
            onClick={() => setExpanded(!expanded)}
            style={{
              background: 'none',
              border: 0,
              font: 'inherit',
              fontSize: 12,
              color: 'inherit',
              cursor: 'pointer',
              padding: 0,
              textAlign: 'left',
            }}
          >
            {expanded ? '▾' : '▸'}
          </button>
        )}

        {/* One link over both lines, as the artboard draws it: the title and
            the key are the same target, and a reader searching for either
            finds the row. The key alone when the prompt file is unreadable --
            repeating it as its own subtitle says nothing twice. */}
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

        <span className="text-muted" style={MONO_CELL} title={meta.data?.default_model}>
          {meta.data?.default_model ?? '—'}
        </span>

        <span
          className="text-muted"
          style={MONO_CELL}
          title={typeof agent.endpoint_path === 'string' ? agent.endpoint_path : undefined}
        >
          {String(agent.endpoint_path ?? '—')}
        </span>

        <span className="text-muted" style={MONO_CELL} title={promptLabel || undefined}>
          {promptLabel || '—'}
        </span>

        <span style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button
            type="button"
            role="switch"
            className="switch"
            aria-checked={enabled}
            aria-label={`${agentKey} ${t.agentsOn}`}
            disabled={!isAdmin}
            onClick={() => draft.setValue(enabledPath, !enabled)}
          >
            <span className="switch-knob" />
          </button>
          <span className="text-muted" style={{ fontSize: 11 }}>
            {t.activeIn} <span data-testid="active-count">{active.length}</span> ·{' '}
            <span data-testid="override-count">{overriders.length}</span> {t.overrides}
          </span>
        </span>
      </div>

      {expanded && (
        <div
          data-testid={`agent-overrides-${agentKey}`}
          style={{
            padding: '8px 14px 12px 58px',
            background: 'var(--color-surface)',
            borderBottom: '1px solid var(--color-divider)',
            display: 'flex',
            flexDirection: 'column',
            gap: 6,
          }}
        >
          <div
            className="text-muted"
            style={{ fontSize: 11, letterSpacing: '.08em', textTransform: 'uppercase' }}
          >
            {t.perProject}
          </div>
          {active.map(({ project, overridden }) => (
            <div
              key={project}
              data-testid={`agent-project-${project}`}
              style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 13 }}
            >
              <span style={{ flex: 1 }}>{project}</span>
              {overridden ? (
                <span className="tag tag-accent" style={{ padding: '1px 6px', fontSize: 10 }}>
                  {t.override}
                </span>
              ) : (
                <span className="text-muted" style={{ fontSize: 10 }}>
                  {t.inherit}
                </span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function Matrix({
  keys,
  disk,
  running,
  lang,
  isAdmin,
}: {
  keys: string[]
  disk: Record<string, unknown>
  running: Record<string, unknown>
  lang: Lang
  isAdmin: boolean
}) {
  const t = useTranslations(lang)
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
        {t.noProjects}
      </div>
    )
  }

  /** What a column header says under the project's name. */
  const columnSub = (project: string): string => {
    const overrides = agentKeys(running).filter(
      (agentKey) => overridingProjects(running, agentKey).indexOf(project) !== -1,
    ).length
    return overrides > 0 ? `${overrides} ${t.overrides}` : t.inheritsGlobal
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {projects.data?.source === 'unavailable' && (
        <div data-testid="projects-unavailable" style={{ fontSize: 12, color: '#a33a2b' }}>
          {t.projectsUnavailable}
        </div>
      )}
      <div className="blueprint" style={{ overflow: 'auto' }}>
        <i className="corner tl" />
        <i className="corner tr" />
        <i className="corner bl" />
        <i className="corner br" />
        <table role="table" style={{ borderCollapse: 'collapse', fontSize: 13, width: '100%' }}>
        <thead>
          <tr>
            <th style={{ textAlign: 'left', padding: '8px 14px', minWidth: 220 }} />
            {columns.map((project) => {
              const inTestBench = fromTestBench.includes(project)
              return (
                <th
                  key={project}
                  role="columnheader"
                  scope="col"
                  data-testid={`column-${project}`}
                  data-in-testbench={String(inTestBench)}
                  style={{
                    padding: '8px 12px',
                    minWidth: 150,
                    textAlign: 'left',
                    verticalAlign: 'bottom',
                    fontWeight: 400,
                    borderLeft: '1px solid var(--color-divider)',
                    borderBottom: '1px solid var(--color-divider)',
                    whiteSpace: 'nowrap',
                  }}
                  title={inTestBench ? project : `${project} · ${t.notInTestBench}`}
                >
                  <div
                    style={{
                      fontFamily: 'var(--font-heading)',
                      fontSize: 15,
                      color: inTestBench ? 'inherit' : '#a33a2b',
                    }}
                  >
                    {project}
                    {!inTestBench && ' ⚠'}
                  </div>
                  <div className="text-muted" style={{ fontSize: 11, fontWeight: 400 }}>
                    {columnSub(project)}
                  </div>
                </th>
              )
            })}
          </tr>
        </thead>
        <tbody>
          {keys.map((agentKey) => {
            // Draft-aware, like the list view's own switch: an agent switched
            // off globally in this same unapplied draft must not show every
            // inheriting project as still running it -- the accessible label
            // of each cell states the resolved value, and it would be lying.
            const globalPath = agentPath(agentKey, 'enabled')
            const inherited =
              draft.valueOf(globalPath, effectiveAgent(running, agentKey, null).enabled) === true
            return (
              <tr key={agentKey}>
                <th
                  role="rowheader"
                  scope="row"
                  className="tb-row"
                  style={{
                    textAlign: 'left',
                    padding: '6px 14px',
                    fontWeight: 400,
                    fontFamily: 'ui-monospace, Menlo, monospace',
                    whiteSpace: 'nowrap',
                    borderBottom: '1px solid var(--color-divider)',
                  }}
                >
                  {agentKey}
                </th>
                {columns.map((project) => {
                  const path = projectAgentPath(project, agentKey, 'enabled')
                  // The cell that carries an opinion is tinted, so the shape
                  // of the overrides is readable across the whole grid before
                  // any single cell is read.
                  const overridden =
                    draft.valueOf(path, valueAt(disk, path)) !== undefined &&
                    draft.valueOf(path, valueAt(disk, path)) !== null
                  return (
                    <td
                      key={project}
                      style={{
                        padding: '4px 12px',
                        borderLeft: '1px solid var(--color-divider)',
                        borderBottom: '1px solid var(--color-divider)',
                        background: overridden ? 'var(--color-accent-100)' : 'transparent',
                      }}
                    >
                      <AgentSwitch
                        path={path}
                        saved={valueAt(disk, path)}
                        inherited={inherited}
                        label={`${agentKey} · ${project}`}
                        readOnly={!isAdmin}
                        lang={lang}
                      />
                    </td>
                  )
                })}
              </tr>
            )
          })}
        </tbody>
        </table>
      </div>
    </div>
  )
}
