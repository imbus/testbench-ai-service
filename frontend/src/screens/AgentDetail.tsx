import { useState } from 'react'
import { useParams } from 'react-router-dom'
import {
  configuredProjects,
  effectiveAgent,
  overridingProjects,
  projectAgentPath,
  projectPath,
  scopedAgentPath,
  type Scope,
} from '../api/agents'
import { useConfig, useProjects, usePromptMeta } from '../api/queries'
import type { ConfigIssue, PromptVarDefinition } from '../api/types'
import { Field } from '../components/Field'
import { ReadOnlyField } from '../components/ReadOnlyField'
import { useTranslations, type Lang } from '../i18n'
import { useDraft } from '../state/draft'
import {
  AGENT_FIELDS,
  AGENT_READONLY_FIELDS,
  promptVarField,
  varDefault,
} from './agentFields'
import { valueAt } from './fields'

function issueFor(issues: ConfigIssue[], key: string): string | undefined {
  return issues.find((entry) => entry.path === key || entry.path.startsWith(key + '.'))?.message
}

/**
 * One agent, in one scope.
 *
 * The scope switcher is what makes this screen serve both the global agent and
 * every project that overrides it: the same controls, addressed at a different
 * table. Choosing a scope is navigation, never an edit — writing an empty
 * override table on selection would put a change in the diff the operator
 * never asked for.
 */
export function AgentDetail({
  lang,
  isAdmin,
  issues = [],
}: {
  lang: Lang
  isAdmin: boolean
  issues?: ConfigIssue[]
}) {
  const t = useTranslations(lang)
  const { agentKey = '' } = useParams()
  const config = useConfig()
  const projects = useProjects()
  const draft = useDraft()
  const [project, setProject] = useState<string | null>(null)

  // Every hook is called here, above the early returns below. This component
  // stays mounted across the loading -> loaded transition, and a hook called
  // only on some renders of the same instance corrupts React's hook order --
  // a hard crash, not a lint nit. So the values `usePromptMeta` needs are
  // derived defensively from a possibly-absent config instead.
  const running = config.data?.running ?? {}
  const disk = config.data?.disk ?? {}
  const globalAgent = effectiveAgent(running, agentKey, null)
  const scope: Scope = project === null ? { kind: 'global' } : { kind: 'project', project }
  const scopedAgent = effectiveAgent(running, agentKey, project)

  // The effective language of the scope being edited. A project's `language`
  // override decides which prompts_dir/<lang>/ its prompt files come from, so
  // reading the global language for such a project would show the variants of
  // an entirely different file.
  const globalLanguage = String(valueAt(running, 'language') ?? 'de')
  const language =
    project === null
      ? globalLanguage
      : String(valueAt(running, projectPath(project, 'language')) ?? globalLanguage)

  const promptFilePath = scopedAgentPath(scope, agentKey, 'prompt.file')
  const draftFile = draft.valueOf(promptFilePath, undefined)
  // Draft-aware: switching the prompt in the form re-reads the new file's
  // variants before the change is applied.
  const promptFile =
    typeof draftFile === 'string' && draftFile
      ? draftFile
      : typeof scopedAgent.prompt?.file === 'string'
        ? (scopedAgent.prompt.file as string)
        : undefined

  const meta = usePromptMeta(language, agentKey, promptFile)

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

  if (Object.keys(globalAgent).length === 0) {
    return (
      <div data-testid="unknown-agent" role="alert" style={{ padding: 28 }}>
        {t.unknownAgent}
      </div>
    )
  }

  const variantPath = scopedAgentPath(scope, agentKey, 'prompt.variant')
  const savedVariant = scopedAgent.prompt?.variant
  const variant = String(
    draft.valueOf(variantPath, savedVariant) ?? meta.data?.default_variant ?? '',
  )

  const variantNames = meta.data?.variants.map((entry) => entry.name)
  const selected = meta.data?.variants.find((entry) => entry.name === variant)
  const declared = selected?.vars ?? {}

  // Variables set in config that the selected variant does not declare. Hiding
  // them would leave values in the file the operator can neither see nor
  // remove.
  const configured = Object.keys(
    (scopedAgent.prompt?.vars as Record<string, unknown> | undefined) ?? {},
  )
  const undeclared = meta.data ? configured.filter((name) => !(name in declared)) : []

  const overriders = overridingProjects(running, agentKey)
  const known = [
    ...(projects.data?.projects ?? []).map((entry) => entry.name),
    ...configuredProjects(running),
  ]
  const addable = [...new Set(known)].filter((name) => !overriders.includes(name))
  const tabs = [...new Set(project !== null ? [...overriders, project] : overriders)]

  /** What this control falls back to when the current scope says nothing. */
  const inherited = (setting: string) =>
    scope.kind === 'global'
      ? undefined
      : { value: valueAt(globalAgent as Record<string, unknown>, setting), label: t.globalScope }

  return (
    <div
      data-testid="agent-detail"
      style={{
        padding: '28px 32px',
        display: 'flex',
        flexDirection: 'column',
        gap: 16,
        maxWidth: 900,
      }}
    >
      <div>
        <h2 style={{ margin: 0, fontSize: 30 }}>{meta.data?.name ?? agentKey}</h2>
        <div
          className="text-muted"
          style={{ fontSize: 12, fontFamily: 'ui-monospace, Menlo, monospace' }}
        >
          {agentKey} · {config.data.config_path}
        </div>
      </div>

      <div role="tablist" style={{ display: 'flex', gap: 18, alignItems: 'center', flexWrap: 'wrap' }}>
        <ScopeTab
          label={t.globalScope}
          selected={project === null}
          onSelect={() => setProject(null)}
        />
        {tabs.map((name) => (
          <ScopeTab
            key={name}
            label={name}
            selected={project === name}
            onSelect={() => setProject(name)}
          />
        ))}
        {addable.length > 0 && (
          <select
            className="input"
            aria-label={t.addProjectOverride}
            value=""
            style={{ fontSize: 13, width: 'auto' }}
            onChange={(event) => {
              if (event.target.value) setProject(event.target.value)
            }}
          >
            <option value="">+ {t.addProjectOverride}</option>
            {addable.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        )}
      </div>

      {meta.isError && (
        <div data-testid="meta-unavailable" style={{ fontSize: 12, color: '#a33a2b' }}>
          {t.promptMetaUnavailable}
        </div>
      )}

      <div data-testid="agent-settings">
        {AGENT_FIELDS(scope, agentKey, variantNames, savedVariant ? String(savedVariant) : undefined).map(
          (spec) => {
            const setting = spec.key.endsWith('enabled')
              ? 'enabled'
              : spec.key.endsWith('prompt.file')
                ? 'prompt.file'
                : 'prompt.variant'
            return isAdmin ? (
              <Field
                key={spec.key}
                spec={spec}
                saved={valueAt(disk, spec.key)}
                issue={issueFor(issues, spec.key)}
                inheritedFrom={inherited(setting)}
                lang={lang}
              />
            ) : (
              <ReadOnlyField
                key={spec.key}
                spec={spec}
                value={valueAt(scopedAgent as Record<string, unknown>, setting)}
              />
            )
          },
        )}
      </div>

      <section data-testid="agent-vars">
        <h3 style={{ margin: '4px 0', fontSize: 16 }}>{t.promptVars}</h3>
        {Object.keys(declared).length === 0 && undeclared.length === 0 ? (
          <div className="text-muted" style={{ fontSize: 12 }}>
            {t.noPromptVars}
          </div>
        ) : (
          <>
            {Object.entries(declared).map(([name, definition]) => (
              <VarField
                key={name}
                scope={scope}
                agentKey={agentKey}
                varName={name}
                definition={definition}
                disk={disk}
                globalAgent={globalAgent as Record<string, unknown>}
                issues={issues}
                isAdmin={isAdmin}
                lang={lang}
              />
            ))}
            {undeclared.map((name) => (
              <div key={name} data-testid={`undeclared-${name}`}>
                <ReadOnlyField
                  spec={{
                    key: `agents.${agentKey}.prompt.vars.${name}`,
                    type: 'text',
                    label: name,
                    hint: t.notDeclaredByVariant,
                  }}
                  value={
                    (scopedAgent.prompt?.vars as Record<string, unknown> | undefined)?.[name]
                  }
                />
              </div>
            ))}
          </>
        )}
      </section>

      <section data-testid="agent-readonly">
        <h3 style={{ margin: '4px 0', fontSize: 16 }}>{t.notEditableHere}</h3>
        {AGENT_READONLY_FIELDS(agentKey).map((spec) => (
          <ReadOnlyField key={spec.key} spec={spec} value={valueAt(running, spec.key)} />
        ))}
      </section>

      {scope.kind === 'project' && isAdmin && (
        <div>
          <button
            type="button"
            className="btn btn-ghost"
            style={{ fontSize: 12 }}
            onClick={() => draft.unsetValue(projectAgentPath(scope.project, agentKey))}
          >
            {t.removeAllOverrides}
          </button>
        </div>
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
      aria-selected={selected}
      onClick={onSelect}
      style={{
        background: 'none',
        border: 0,
        borderBottom: `2px solid ${selected ? 'var(--color-accent)' : 'transparent'}`,
        padding: '6px 0',
        font: 'inherit',
        fontSize: 14,
        color: 'inherit',
        opacity: selected ? 1 : 0.7,
        cursor: 'pointer',
      }}
    >
      {label}
    </button>
  )
}

/**
 * One prompt variable, typed by its declaration in the prompt YAML.
 *
 * An unset variable inherits twice over: from the project's global override if
 * there is one, and from the prompt's own `default_value` if there is not. The
 * note names whichever applies, so the operator can see what the agent will
 * actually receive.
 */
function VarField({
  scope,
  agentKey,
  varName,
  definition,
  disk,
  globalAgent,
  issues,
  isAdmin,
  lang,
}: {
  scope: Scope
  agentKey: string
  varName: string
  definition: PromptVarDefinition
  disk: Record<string, unknown>
  globalAgent: Record<string, unknown>
  issues: ConfigIssue[]
  isAdmin: boolean
  lang: Lang
}) {
  const t = useTranslations(lang)
  const spec = promptVarField(scope, agentKey, varName, definition)
  const saved = valueAt(disk, spec.key)

  const fromGlobal = valueAt(globalAgent, `prompt.vars.${varName}`)
  const inheritedValue = scope.kind === 'project' ? (fromGlobal ?? varDefault(definition)) : varDefault(definition)
  const label =
    scope.kind === 'project' && fromGlobal !== undefined ? t.globalScope : t.promptDefault

  if (!isAdmin) return <ReadOnlyField spec={spec} value={saved ?? inheritedValue} />

  return (
    <Field
      spec={spec}
      saved={saved}
      issue={issueFor(issues, spec.key)}
      inheritedFrom={{ value: inheritedValue, label }}
      lang={lang}
    />
  )
}
