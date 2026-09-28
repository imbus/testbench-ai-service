import { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  agentKeys,
  agentPath,
  configuredProjects,
  effectiveAgent,
  projectAgentPath,
  projectPath,
} from '../api/agents'
import { useRefreshProjects } from '../api/mutations'
import { useConfig, useProjects } from '../api/queries'
import type { ConfigIssue } from '../api/types'
import { AgentSwitch } from '../components/AgentSwitch'
import { useTranslations, type Lang } from '../i18n'
import { useDraft } from '../state/draft'
import { LANGUAGES } from './agentFields'
import { valueAt } from './fields'

function issueFor(issues: ConfigIssue[], key: string): string | undefined {
  return issues.find((entry) => entry.path === key || entry.path.startsWith(key + '.'))?.message
}

/**
 * Which TestBench projects override which agents.
 *
 * Cards are the **union** of the cached TestBench list and the projects
 * `config.toml` declares. A config-only project keeps its card, flagged: it
 * usually means the project was renamed or deleted in TestBench, which is
 * exactly the case an operator has to be able to see and clean up.
 */
export function Projects({
  lang,
  isAdmin,
  issues = [],
}: {
  lang: Lang
  isAdmin: boolean
  issues?: ConfigIssue[]
}) {
  const t = useTranslations(lang)
  const config = useConfig()
  const projects = useProjects()
  const refresh = useRefreshProjects()
  const [typed, setTyped] = useState<string[]>([])
  const [pending, setPending] = useState('')

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
  // missing either one must render an empty screen, not crash.
  const disk = config.data.disk ?? {}
  const running = config.data.running ?? {}
  const fromTestBench = (projects.data?.projects ?? []).map((entry) => entry.name)
  const names = [...new Set([...fromTestBench, ...configuredProjects(running), ...typed])]
  const keys = agentKeys(running)
  const unavailable = projects.data?.source === 'unavailable'

  return (
    <div
      style={{
        padding: '28px 32px',
        display: 'flex',
        flexDirection: 'column',
        gap: 20,
        maxWidth: 1400,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 16, flexWrap: 'wrap' }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <h2 style={{ margin: 0, fontSize: 30 }}>{t.projects}</h2>
          <div
            className="text-muted"
            style={{ fontSize: 12, fontFamily: 'ui-monospace, Menlo, monospace' }}
          >
            [testbench-ai-service.projects] · {config.data.config_path}
          </div>
        </div>
        {projects.data?.fetched_at && (
          <span data-testid="projects-fetched-at" className="text-muted" style={{ fontSize: 11 }}>
            {t.fetchedAt} {new Date(projects.data.fetched_at).toLocaleString()}
          </span>
        )}
        {/* Admin only: the refresh spends the stored TestBench credential on an
            outbound call, and the route is admin-gated to match. */}
        {isAdmin && (
          <button
            type="button"
            className="btn btn-ghost"
            style={{ fontSize: 12 }}
            disabled={refresh.isPending}
            onClick={() => refresh.mutate()}
          >
            {refresh.isPending ? t.refreshing : t.refresh}
          </button>
        )}
      </div>

      {unavailable && (
        <div data-testid="projects-unavailable" style={{ fontSize: 12, color: '#a33a2b' }}>
          {t.projectsUnavailable} {projects.data?.error}
        </div>
      )}

      {/* A refresh that never came back is not the same as a project list that
          is merely stale, and the row above cannot say so: the route answers
          200 with the previous list even when the fetch failed, and a 403 or a
          dropped connection never reaches it at all. */}
      {refresh.isError && (
        <div data-testid="refresh-failed" role="alert" style={{ fontSize: 12, color: '#a33a2b' }}>
          {t.refreshFailed} {(refresh.error as Error)?.message}
        </div>
      )}

      {/* Only when the console genuinely cannot know the real names. Typing a
          name that has to match TestBench character for character is a
          footgun, and not one worth offering while the real list is in hand. */}
      {unavailable && (
        <div
          data-testid="add-by-name"
          style={{
            display: 'flex',
            gap: 8,
            alignItems: 'center',
            flexWrap: 'wrap',
            fontSize: 12,
          }}
        >
          <label htmlFor="add-project">{t.projectName}</label>
          <input
            className="input"
            id="add-project"
            type="text"
            style={{ width: 220 }}
            value={pending}
            onChange={(event) => setPending(event.target.value)}
          />
          <button
            type="button"
            className="btn btn-ghost"
            onClick={() => {
              const name = pending.trim()
              if (!name) return
              setTyped((current) => (current.includes(name) ? current : [...current, name]))
              setPending('')
            }}
          >
            {t.add}
          </button>
          <span className="text-muted">{t.projectNameExact}</span>
        </div>
      )}

      {names.length === 0 ? (
        <div className="text-muted" style={{ fontSize: 13 }}>
          {t.noProjects}
        </div>
      ) : (
        <div
          style={{
            display: 'grid',
            // Wide enough for an agent row (switch, name, variant, override
            // tag, state) on one line; min() keeps a narrow window from
            // scrolling sideways.
            gridTemplateColumns: 'repeat(auto-fill, minmax(min(460px, 100%), 1fr))',
            gap: 24,
          }}
        >
          {names.map((name) => (
            <ProjectCard
              key={name}
              name={name}
              inTestBench={fromTestBench.includes(name)}
              agentKeys={keys}
              disk={disk}
              running={running}
              issues={issues}
              isAdmin={isAdmin}
              lang={lang}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function ProjectCard({
  name,
  inTestBench,
  agentKeys: keys,
  disk,
  running,
  issues,
  isAdmin,
  lang,
}: {
  name: string
  inTestBench: boolean
  agentKeys: string[]
  disk: Record<string, unknown>
  running: Record<string, unknown>
  issues: ConfigIssue[]
  isAdmin: boolean
  lang: Lang
}) {
  const t = useTranslations(lang)
  const draft = useDraft()

  const block = valueAt(running, projectPath(name))
  const declared = block !== undefined
  // `running` is a pydantic dump, so a project without an llm_config carries
  // an explicit null here rather than nothing at all. Testing for `undefined`
  // alone would put an "llm_config · edit in config.toml" panel reading
  // `null` on every declared project.
  const llmConfigValue = valueAt(running, projectPath(name, 'llm_config'))
  const llmConfig = llmConfigValue === null ? undefined : llmConfigValue
  const globalLanguage = valueAt(running, 'language')

  // What the header chip counts: every key this project's block carries. The
  // draft is not consulted -- the chip describes the file, and the pending
  // banner already describes the draft.
  const overrideCount = (() => {
    const table = block !== null && typeof block === 'object' ? (block as Record<string, unknown>) : {}
    const agents = table.agents
    const perAgent =
      agents !== null && typeof agents === 'object' ? Object.keys(agents as object).length : 0
    return perAgent + (table.language ? 1 : 0) + (table.llm_config ? 1 : 0)
  })()

  const languagePath = projectPath(name, 'language')
  const savedLanguage = valueAt(disk, languagePath)
  const language = draft.valueOf(languagePath, savedLanguage)
  const languageIssue = issueFor(issues, languagePath)

  return (
    <section
      className="card blueprint"
      data-testid={`project-${name}`}
      data-in-testbench={String(inTestBench)}
      // minWidth 0: a grid item otherwise refuses to shrink below its content
      // and pushes past its column.
      style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 12, minWidth: 0 }}
    >
      {/* The frame's corner marks. Hidden under [data-corners=soft], but they
          are what the square-cornered brand draws, so they are always emitted
          -- and always first, as the design system's selectors expect. */}
      <i className="corner tl" />
      <i className="corner tr" />
      <i className="corner bl" />
      <i className="corner br" />

      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <h3 className="card-title" style={{ margin: 0, fontSize: 19 }}>
          {name}
        </h3>
        <div style={{ flex: 1 }} />
        {!inTestBench && (
          <span style={{ fontSize: 11, color: '#a33a2b' }}>⚠ {t.notInTestBench}</span>
        )}
        {overrideCount > 0 ? (
          <span className="tag tag-accent">
            {overrideCount} {t.overrides}
          </span>
        ) : (
          <span className="tag tag-neutral">{t.inheritsGlobal}</span>
        )}
      </div>

      {/* Three states, one control: the language override is exactly the
          inherit/de/en choice, so it reads as a segmented switch rather than a
          select whose empty option means "inherit". */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          fontSize: 13,
          flexWrap: 'wrap',
        }}
      >
        <span
          id={`${encodeURIComponent(languagePath)}-label`}
          style={{ fontFamily: 'ui-monospace, Menlo, monospace', fontSize: 12 }}
        >
          language
        </span>
        {isAdmin ? (
          <div
            className="seg"
            role="radiogroup"
            aria-labelledby={`${encodeURIComponent(languagePath)}-label`}
          >
            <label className="seg-opt" style={{ padding: '3px 10px', fontSize: 12 }}>
              <input
                type="radio"
                name={`lang-${encodeURIComponent(name)}`}
                checked={language === undefined || language === null}
                onChange={() => draft.unsetValue(languagePath)}
              />
              {t.inherit} ({String(globalLanguage ?? '')})
            </label>
            {LANGUAGES.map((option) => (
              <label key={option} className="seg-opt" style={{ padding: '3px 10px', fontSize: 12 }}>
                <input
                  type="radio"
                  name={`lang-${encodeURIComponent(name)}`}
                  checked={language === option}
                  onChange={() => draft.setValue(languagePath, option)}
                />
                {option}
              </label>
            ))}
          </div>
        ) : (
          <span className="text-muted" style={{ fontSize: 12 }}>
            {String(valueAt(running, languagePath) ?? globalLanguage ?? '')}
          </span>
        )}
        {draft.isChanged(languagePath) && (
          <button
            type="button"
            className="btn btn-ghost"
            style={{ fontSize: 11, padding: '0 6px' }}
            onClick={() => draft.revert(languagePath)}
          >
            {t.revert}
          </button>
        )}
      </div>
      {languageIssue && (
        <span role="alert" style={{ fontSize: 11, color: '#a33a2b' }}>
          {languageIssue}
        </span>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <div className="text-muted" style={{ fontSize: 11 }}>
          {t.agents}
        </div>
        {keys.map((agentKey) => {
          const path = projectAgentPath(name, agentKey, 'enabled')
          const scoped = effectiveAgent(running, agentKey, name)
          const variant = scoped.prompt?.variant
          const hasOverride = valueAt(disk, path) !== undefined
          return (
            <div
              key={agentKey}
              className="tb-row"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                fontSize: 13,
                padding: '4px 0',
                borderTop: '1px solid var(--color-divider)',
              }}
            >
              <AgentSwitch
                path={path}
                saved={valueAt(disk, path)}
                inherited={
                  // Draft-aware: an agent switched off globally in this same
                  // unapplied draft must not read as running here.
                  draft.valueOf(
                    agentPath(agentKey, 'enabled'),
                    effectiveAgent(running, agentKey, null).enabled,
                  ) === true
                }
                label={`${agentKey} · ${name}`}
                readOnly={!isAdmin}
                lang={lang}
              >
                <span
                  style={{
                    fontFamily: 'ui-monospace, Menlo, monospace',
                    flex: 1,
                    minWidth: 0,
                    overflowWrap: 'anywhere',
                  }}
                >
                  {agentKey}
                </span>
                {/* Which prompt this agent runs here, since the switch only says
                    whether it runs at all. */}
                {typeof variant === 'string' && variant && (
                  <span
                    className="text-muted"
                    style={{
                      fontSize: 11,
                      fontFamily: 'ui-monospace, Menlo, monospace',
                      overflowWrap: 'anywhere',
                    }}
                  >
                    {variant}
                  </span>
                )}
                {hasOverride && (
                  <span className="tag tag-accent" style={{ padding: '1px 6px', fontSize: 10 }}>
                    {t.override}
                  </span>
                )}
              </AgentSwitch>
            </div>
          )
        })}
      </div>

      {/* The project's llm_config, summarised. Phase 4d made it editable on
          the LLM screen; this stays as the at-a-glance view of what the
          project overrides, and links there. */}
      {llmConfig !== undefined && (
        <div
          data-testid="project-llm-config"
          style={{
            fontSize: 12,
            padding: '8px 10px',
            background: 'var(--color-surface)',
            border: '1px solid var(--color-divider)',
            borderRadius: 4,
          }}
        >
          <div style={{ marginBottom: 4 }}>
            <strong>llm_config</strong> ·{' '}
            {/* <Link>, never <a href>: a full page load bypasses the
                unsaved-changes guard and drops the operator's queued edits.
                encodeURIComponent, so a project called `Release 2.0` addresses
                itself on the other side rather than some other project. */}
            <Link to={`/admin/llm?project=${encodeURIComponent(name)}`}>{t.editLlmConfig}</Link>
            <div className="text-muted" style={{ fontSize: 11 }}>{t.removedWithProject}</div>
          </div>
          <pre
            style={{
              margin: 0,
              whiteSpace: 'pre-wrap',
              fontFamily: 'ui-monospace, Menlo, monospace',
              fontSize: 11,
            }}
          >
            {JSON.stringify(llmConfig, null, 2)}
          </pre>
        </div>
      )}

      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <span className="card-meta" style={{ fontFamily: 'ui-monospace, Menlo, monospace' }}>
          [testbench-ai-service.{projectPath(name)}]
        </span>
        <div style={{ flex: 1 }} />
        {isAdmin && declared && (
          <button
            type="button"
            className="btn btn-ghost"
            style={{ fontSize: 12 }}
            onClick={() => draft.unsetSubtree(projectPath(name))}
          >
            {t.removeAllOverrides}
          </button>
        )}
      </div>
    </section>
  )
}
