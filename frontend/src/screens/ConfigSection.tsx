import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { configuredProjects, llmOverridingProjects, scopedLlmPath, type Scope } from '../api/agents'
import type { ConfigIssue, ExtraModelEntry } from '../api/types'
import { useConfig, useModels, useProjects } from '../api/queries'
import { Field } from '../components/Field'
import { ModelTable } from '../components/ModelTable'
import { ReadOnlyField } from '../components/ReadOnlyField'
import { ScopeTabs } from '../components/ScopeTabs'
import { useTranslations, type Lang } from '../i18n'
import { LOGGING_FIELDS, SERVICE_TABS, llmFields, valueAt, type FieldSpec } from './fields'

type Section = 'service' | 'llm' | 'logging'

const TITLE_KEY: Record<Section, 'service' | 'llm' | 'logging'> = {
  service: 'service',
  llm: 'llm',
  logging: 'logging',
}

const TOML_SECTION: Record<Section, string> = {
  service: '[testbench-ai-service]',
  llm: '[testbench-ai-service.llm_config]',
  logging: '[testbench-ai-service.logging.console] · [.file]',
}

/**
 * Check if an issue path matches a field key or a child path within it.
 * Matches exact equality or paths starting with key + '.' to handle array
 * elements reported by pydantic (e.g., trusted_proxies.0 matches trusted_proxies).
 * Must not be bare startsWith — that would make port match port_extra.
 */
function issueMatchesField(issuePath: string, fieldKey: string): boolean {
  return issuePath === fieldKey || issuePath.startsWith(fieldKey + '.')
}

export function ConfigSection({
  section,
  lang,
  isAdmin,
  issues = [],
}: {
  section: Section
  lang: Lang
  isAdmin: boolean
  /** Field-addressed validation failures from the last preview or apply. */
  issues?: ConfigIssue[]
}) {
  const t = useTranslations(lang)
  const config = useConfig()
  const projects = useProjects()
  const [params, setParams] = useSearchParams()
  const [tab, setTab] = useState(SERVICE_TABS[0].key)

  // Every hook is called here, above the early returns below -- the same
  // hook-order rule AgentDetail documents. This component stays mounted across
  // the loading -> loaded transition, so a hook called on only some renders of
  // the same instance corrupts React's hook order.
  //
  // Only the LLM screen has scopes; on Service and Logging the parameter is
  // ignored rather than being allowed to put those screens in a state they
  // cannot render.
  const project = section === 'llm' ? params.get('project') : null
  const scope: Scope = project === null ? { kind: 'global' } : { kind: 'project', project }
  const catalogue = useModels(project ?? undefined)

  if (config.isLoading) return <div style={{ padding: 28 }}>…</div>
  if (config.isError || !config.data) {
    // Same structure as Status.tsx's error branch: the primary line is
    // always the translated fallback — never the raw, often-English,
    // backend-shaped error text — so this alert can never show untranslated
    // copy regardless of what threw. The raw message, if any, is shown
    // underneath only as diagnostic detail, guarded so an empty detail
    // renders nothing.
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

  const running = config.data.running
  let fields: FieldSpec[]
  if (section === 'service') {
    fields = (SERVICE_TABS.find((entry) => entry.key === tab) ?? SERVICE_TABS[0]).fields
  } else {
    fields = section === 'llm' ? llmFields(scope) : LOGGING_FIELDS
  }

  // For Service tabs, determine which have issues
  const tabIssueCount = (tabKey: string): number => {
    const tabFields = SERVICE_TABS.find((entry) => entry.key === tabKey)?.fields ?? []
    return issues.filter((issue) =>
      tabFields.some((field) => issueMatchesField(issue.path, field.key)),
    ).length
  }

  // From `disk`, not `running`: `running` reports an llm_config table for a
  // project only when it has one, but reading the file is what "this project
  // overrides the LLM config" means, and it is the same source the fields are
  // measured against.
  const llmTabs = llmOverridingProjects(config.data.disk)
  // A project addressed by the URL gets a tab even before it has a block, so
  // the Projects screen can link straight into an override that does not exist
  // yet.
  const tabs = [...new Set(project !== null ? [...llmTabs, project] : llmTabs)]
  const known = [
    ...(projects.data?.projects ?? []).map((entry) => entry.name),
    ...configuredProjects(running),
  ]
  const addable = [...new Set(known)].filter((name) => !tabs.includes(name))
  // Presence only. No endpoint returns a credential value and no code here may
  // print one. Defaulted rather than assumed: `/models` can be absent, failed
  // or still loading, and none of those is worth a crashed screen.
  const credentials = catalogue.data?.providers ?? []

  return (
    <div
      style={{
        padding: '28px 32px',
        display: 'flex',
        flexDirection: 'column',
        gap: 20,
        maxWidth: 1100,
      }}
    >
      {/* The artboard sets the screen title and the TOML section it edits on
          one line, so the section reads as the subject of the heading rather
          than as a caption under it. */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
        <h2 style={{ margin: 0, fontSize: 30 }}>{t[TITLE_KEY[section]]}</h2>
        <span
          className="text-muted"
          style={{ fontSize: 12, fontFamily: 'ui-monospace, Menlo, monospace' }}
        >
          {TOML_SECTION[section]} · {config.data.config_path}
        </span>
      </div>

      {section === 'llm' && (
        <>
          <ScopeTabs
            projects={tabs}
            selected={project}
            addable={addable}
            onSelect={(next) => {
              // Navigation, not an edit. Replacing the whole parameter set is
              // deliberate: this screen owns no other search parameter, and a
              // stale one left behind would outlive the scope it described.
              setParams(next === null ? {} : { project: next })
            }}
            globalLabel={t.globalScope}
            addLabel={t.addProjectOverride}
          />
          {project !== null && (
            <div className="text-muted" style={{ fontSize: 12 }}>
              {t.llmScopeHint}
            </div>
          )}
        </>
      )}

      {section === 'service' && (
        <div
          role="tablist"
          style={{ display: 'flex', gap: 20, borderBottom: '1px solid var(--color-divider)' }}
        >
          {SERVICE_TABS.map((entry) => {
            const count = tabIssueCount(entry.key)
            return (
              <button
                key={entry.key}
                role="tab"
                aria-selected={tab === entry.key}
                aria-label={`${t[entry.labelKey]}${count > 0 ? ` (${count} ${count === 1 ? 'issue' : 'issues'})` : ''}`}
                onClick={() => setTab(entry.key)}
                style={{
                  background: 'none',
                  border: 0,
                  borderBottom: `2px solid ${tab === entry.key ? 'var(--color-accent)' : 'transparent'}`,
                  padding: '8px 0',
                  font: 'inherit',
                  fontSize: 14,
                  color: 'inherit',
                  opacity: tab === entry.key ? 1 : 0.7,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                }}
              >
                {t[entry.labelKey]}
                {count > 0 && (
                  <span
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      width: 18,
                      height: 18,
                      borderRadius: '50%',
                      background: '#a33a2b',
                      color: '#fff',
                      fontSize: 11,
                      fontWeight: 600,
                      flexShrink: 0,
                    }}
                  >
                    {count}
                  </span>
                )}
              </button>
            )
          })}
        </div>
      )}

      <div style={{ maxWidth: 860 }}>
        {fields.map((spec) => {
          const issue = issues.find((entry) => issueMatchesField(entry.path, spec.key))?.message
          // In project scope the saved value comes from `disk` ONLY. `running`
          // is a pydantic dump, so a project stating just `timeout` still
          // carries provider="openai" and auth_method="api_key" -- the model's
          // defaults, not the operator's choices. Falling back to it would
          // show every field as overridden, and would offer the operator a
          // default to accidentally write into their file. Measured
          // 2026-09-18; see the plan's Task 6.
          //
          // Globally the fallback is right and stays: the draft is "what will
          // be written", so it is measured against the file, but a default the
          // file omits is genuinely the value in force.
          const saved =
            scope.kind === 'project'
              ? valueAt(config.data.disk, spec.key)
              : (valueAt(config.data.disk, spec.key) ?? valueAt(running, spec.key))
          // What applies when this project says nothing. Read from `running`'s
          // *global* llm_config, where a dump filled with defaults is exactly
          // what is in force.
          const inherited =
            scope.kind === 'project'
              ? valueAt(running, scopedLlmPath({ kind: 'global' }, spec.setting))
              : undefined
          // Non-admins keep the phase-1 read-only rendering unchanged rather
          // than getting a form full of disabled inputs.
          return isAdmin ? (
            <Field
              key={spec.key}
              spec={spec}
              saved={saved}
              inheritedFrom={
                scope.kind === 'project' ? { value: inherited, label: t.globalScope } : undefined
              }
              issue={issue}
              lang={lang}
            />
          ) : (
            <ReadOnlyField
              key={spec.key}
              spec={spec}
              // The same two sources in the same order as the editable path.
              // A read-only viewer has no control to notice a wrong value on,
              // so showing them the filled default would be the harder error.
              value={scope.kind === 'project' ? (saved ?? inherited) : valueAt(running, spec.key)}
            />
          )
        })}
      </div>

      {section === 'llm' && scope.kind === 'global' && (
        <ModelTable
          entries={
            // Same source ordering every other field on this screen uses:
            // the file first (what the draft is measured against), the
            // fully-defaulted running config only if the file is silent.
            ((valueAt(config.data.disk, 'llm_config.extra_models') ??
              valueAt(running, 'llm_config.extra_models')) ??
              {}) as Record<string, ExtraModelEntry>
          }
          issues={issues}
          readOnly={!isAdmin}
          lang={lang}
        />
      )}

      {section === 'llm' && scope.kind === 'project' && credentials.length > 0 && (
        <div style={{ maxWidth: 860 }}>
          <h3 style={{ fontSize: 16, marginBottom: 8 }}>{t.credentialsHeading}</h3>
          {credentials.map((entry) => (
            <div key={entry.provider} className="text-muted" style={{ fontSize: 12 }}>
              <strong>{entry.provider}</strong> —{' '}
              {entry.key_present ? t.projectKeyPresent : t.projectKeyAbsent}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
