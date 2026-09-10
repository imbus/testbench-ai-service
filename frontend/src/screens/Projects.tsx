import { useState } from 'react'
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
import { Field } from '../components/Field'
import { ReadOnlyField } from '../components/ReadOnlyField'
import { TriState } from '../components/TriState'
import { useTranslations, type Lang } from '../i18n'
import { useDraft } from '../state/draft'
import { PROJECT_FIELDS } from './agentFields'
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
        gap: 16,
        maxWidth: 1000,
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
        names.map((name) => (
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
        ))
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

  return (
    <section
      data-testid={`project-${name}`}
      data-in-testbench={String(inTestBench)}
      style={{
        border: '1px solid var(--color-divider)',
        borderRadius: 6,
        padding: '14px 16px',
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
        <h3 style={{ margin: 0, fontSize: 17 }}>{name}</h3>
        {!inTestBench && (
          <span style={{ fontSize: 11, color: '#a33a2b' }}>⚠ {t.notInTestBench}</span>
        )}
      </div>

      {isAdmin ? (
        PROJECT_FIELDS(name).map((spec) => (
          <Field
            key={spec.key}
            spec={spec}
            saved={valueAt(disk, spec.key)}
            issue={issueFor(issues, spec.key)}
            inheritedFrom={{ value: globalLanguage, label: t.globalScope }}
            lang={lang}
          />
        ))
      ) : (
        PROJECT_FIELDS(name).map((spec) => (
          <ReadOnlyField key={spec.key} spec={spec} value={valueAt(running, spec.key) ?? globalLanguage} />
        ))
      )}

      <div>
        <div className="text-muted" style={{ fontSize: 11, marginBottom: 6 }}>
          {t.agents}
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 14 }}>
          {keys.map((agentKey) => {
            const path = projectAgentPath(name, agentKey, 'enabled')
            return (
              <div
                key={agentKey}
                style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12 }}
              >
                <TriState
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
                />
                <span style={{ fontFamily: 'ui-monospace, Menlo, monospace' }}>{agentKey}</span>
              </div>
            )
          })}
        </div>
      </div>

      {/* D8 keeps the per-project surface to language and agents. A project
          that already carries an llm_config is still shown: silently hiding a
          block that is in the file would misrepresent the configuration. */}
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
            <strong>llm_config</strong> · {t.editInConfigToml}
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

      {isAdmin && declared && (
        <div>
          <button
            type="button"
            className="btn btn-ghost"
            style={{ fontSize: 12 }}
            onClick={() => draft.unsetSubtree(projectPath(name))}
          >
            {t.removeAllOverrides}
          </button>
        </div>
      )}
    </section>
  )
}
