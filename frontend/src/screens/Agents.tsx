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
import { TriState } from '../components/TriState'
import { useTranslations, type Lang } from '../i18n'
import { useDraft } from '../state/draft'
import { valueAt } from './fields'

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
        gap: 16,
        maxWidth: 1100,
      }}
    >
      <div>
        <h2 style={{ margin: 0, fontSize: 30 }}>{t.agents}</h2>
        <div
          className="text-muted"
          style={{ fontSize: 12, fontFamily: 'ui-monospace, Menlo, monospace' }}
        >
          [testbench-ai-service.agents] · {config.data.config_path}
        </div>
      </div>

      <div role="tablist" style={{ display: 'flex', gap: 18 }}>
        {(['list', 'matrix'] as const).map((entry) => (
          <button
            key={entry}
            role="tab"
            aria-selected={view === entry}
            onClick={() => setView(entry)}
            style={{
              background: 'none',
              border: 0,
              borderBottom: `2px solid ${view === entry ? 'var(--color-accent)' : 'transparent'}`,
              padding: '6px 0',
              font: 'inherit',
              fontSize: 14,
              color: 'inherit',
              opacity: view === entry ? 1 : 0.7,
              cursor: 'pointer',
            }}
          >
            {entry === 'list' ? t.viewList : t.viewMatrix}
          </button>
        ))}
      </div>

      {view === 'list' ? (
        <div>
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

  const overriders = overridingProjects(running, agentKey)
  const enabledPath = agentPath(agentKey, 'enabled')
  const savedEnabled = valueAt(disk, enabledPath)
  const enabled = draft.valueOf(enabledPath, savedEnabled ?? agent.enabled) === true

  return (
    <div
      data-testid={`agent-row-${agentKey}`}
      style={{ borderBottom: '1px solid var(--color-divider)', padding: '10px 0' }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
        <button
          type="button"
          role="switch"
          aria-checked={enabled}
          aria-label={`${agentKey} ${t.agentsOn}`}
          disabled={!isAdmin}
          onClick={() => draft.setValue(enabledPath, !enabled)}
          style={{
            width: 36,
            height: 20,
            flex: 'none',
            borderRadius: 10,
            border: '1px solid var(--color-divider)',
            background: enabled ? 'var(--color-accent)' : 'var(--color-surface)',
            position: 'relative',
            cursor: isAdmin ? 'pointer' : 'default',
            opacity: isAdmin ? 1 : 0.5,
            padding: 0,
          }}
        >
          <span
            style={{
              position: 'absolute',
              top: 2,
              left: enabled ? 18 : 2,
              width: 14,
              height: 14,
              borderRadius: 7,
              background: enabled ? '#fff' : 'var(--color-text)',
              transition: 'left .15s',
            }}
          />
        </button>

        <div style={{ flex: 1, minWidth: 0 }}>
          <Link
            to={`/admin/agents/${encodeURIComponent(agentKey)}`}
            style={{
              color: 'inherit',
              fontSize: 14,
              fontFamily: 'ui-monospace, Menlo, monospace',
            }}
          >
            {agentKey}
          </Link>
          <div className="text-muted" style={{ fontSize: 11 }}>
            {meta.data?.name ?? '—'}
          </div>
        </div>

        <div
          className="text-muted"
          style={{ fontSize: 12, fontFamily: 'ui-monospace, Menlo, monospace' }}
        >
          {String(agent.endpoint_path ?? '—')}
        </div>

        {/* Only an expander when there is something to expand. A control
            that announces itself as collapsible and then opens "no overrides"
            is noise, and it is the row's only interactive element besides the
            switch. */}
        {overriders.length === 0 ? (
          <span
            style={{ fontSize: 12, display: 'flex', alignItems: 'center', gap: 6, opacity: 0.8 }}
          >
            <span data-testid="override-count">0</span>
            <span>{t.overrides}</span>
          </span>
        ) : (
          <button
            type="button"
            aria-expanded={expanded}
            aria-label={`${overriders.length} ${t.overrides}`}
            onClick={() => setExpanded(!expanded)}
            style={{
              background: 'none',
              border: 0,
              font: 'inherit',
              fontSize: 12,
              color: 'inherit',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              opacity: 0.8,
            }}
          >
            <span data-testid="override-count">{overriders.length}</span>
            <span>{t.overrides}</span>
          </button>
        )}
      </div>

      {expanded && (
        <div
          data-testid={`agent-overrides-${agentKey}`}
          style={{ padding: '8px 0 2px 50px', display: 'flex', flexWrap: 'wrap', gap: 10 }}
        >
          {overriders.length === 0 ? (
            <span className="text-muted" style={{ fontSize: 12 }}>
              {t.noOverrides}
            </span>
          ) : (
            overriders.map((project) => (
              <span
                key={project}
                style={{
                  fontSize: 12,
                  padding: '2px 8px',
                  borderRadius: 10,
                  background: 'var(--color-surface)',
                  border: '1px solid var(--color-divider)',
                }}
              >
                {project}
              </span>
            ))
          )}
        </div>
      )}
    </div>
  )
}

/**
 * Agents × projects, one tri-state per cell.
 *
 * Columns are the **union** of the cached TestBench list and the projects that
 * `config.toml` declares. A config-only project keeps its column and is
 * flagged: dropping it would hide an override the operator has to be able to
 * find, and that case is exactly the one needing attention.
 */
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

  return (
    <div style={{ overflowX: 'auto' }}>
      {projects.data?.source === 'unavailable' && (
        <div
          data-testid="projects-unavailable"
          style={{ fontSize: 12, marginBottom: 8, color: '#a33a2b' }}
        >
          {t.projectsUnavailable}
        </div>
      )}
      <table role="table" style={{ borderCollapse: 'collapse', fontSize: 13 }}>
        <thead>
          <tr>
            <th style={{ textAlign: 'left', padding: '6px 12px 6px 0' }} />
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
                    padding: '6px 4px',
                    fontWeight: 500,
                    // Long project names in a narrow column: rotate rather
                    // than let the grid grow past the viewport.
                    writingMode: 'vertical-rl',
                    textOrientation: 'mixed',
                    whiteSpace: 'nowrap',
                    color: inTestBench ? 'inherit' : '#a33a2b',
                  }}
                  title={inTestBench ? project : `${project} · ${t.notInTestBench}`}
                >
                  {project}
                  {!inTestBench && ' ⚠'}
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
                  style={{
                    textAlign: 'left',
                    padding: '4px 12px 4px 0',
                    fontWeight: 400,
                    fontFamily: 'ui-monospace, Menlo, monospace',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {agentKey}
                </th>
                {columns.map((project) => {
                  const path = projectAgentPath(project, agentKey, 'enabled')
                  return (
                    <td key={project} style={{ padding: 2, textAlign: 'center' }}>
                      <TriState
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
  )
}
