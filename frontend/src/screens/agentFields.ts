/**
 * Field specs for the Agents and Projects screens (design §5.4).
 *
 * These are **functions**, unlike `SERVICE_TABS` / `LLM_FIELDS` /
 * `LOGGING_FIELDS`, because the path a control writes to depends on scope: the
 * same "enabled" switch addresses `agents.<key>.enabled` globally and
 * `projects."<name>".agents.<key>.enabled` inside a project. The prompt
 * variables go further and depend on the *prompt file*, which only the
 * metadata endpoint knows.
 *
 * Every path goes through the tokenizer's `joinPath`, so a project called
 * `Release 2.0` is quoted and a project called `My Project` is not — a
 * hand-built path for the first would address nothing, silently.
 */
import { agentPath, projectAgentPath, projectPath, type Scope } from '../api/agents'
import { joinPath } from '../api/paths'
import type { PromptVarDefinition } from '../api/types'
import type { FieldSpec } from './fields'

const LANGUAGES = ['de', 'en']

function scopedPath(scope: Scope, agentKey: string, setting: string): string {
  return scope.kind === 'global'
    ? agentPath(agentKey, setting)
    : projectAgentPath(scope.project, agentKey, setting)
}

/**
 * The editable settings of one agent, in the given scope.
 *
 * `variants` and `configuredVariant` come from the prompt metadata and the
 * current draft respectively. When metadata is unavailable — a prompt file
 * that moved gives a clean 404 — the variant stays a free-text input rather
 * than disappearing: the operator has to be able to fix the very path that
 * caused the 404.
 */
export function AGENT_FIELDS(
  scope: Scope,
  agentKey: string,
  variants?: string[],
  configuredVariant?: string,
): FieldSpec[] {
  return [
    {
      key: scopedPath(scope, agentKey, 'enabled'),
      type: 'bool',
      hint: 'Whether this agent registers its endpoint and runs',
    },
    {
      key: scopedPath(scope, agentKey, 'prompt.file'),
      type: 'text',
      hint: 'Prompt YAML, relative to prompts_dir/<language>/',
    },
    variantField(scope, agentKey, variants, configuredVariant),
  ]
}

function variantField(
  scope: Scope,
  agentKey: string,
  variants: string[] | undefined,
  configuredVariant: string | undefined,
): FieldSpec {
  const key = scopedPath(scope, agentKey, 'prompt.variant')
  const hint = "Which variant of the prompt to use. Empty uses the prompt's default_variant."
  if (!variants) return { key, type: 'text', hint }

  // A configured variant the prompt no longer declares is still offered, so
  // the select does not silently rewrite it to the first option the moment the
  // screen renders. It leads, because it is the value in force.
  const options =
    configuredVariant && !variants.includes(configuredVariant)
      ? [configuredVariant, ...variants]
      : variants
  return { key, type: 'select', options, hint }
}

/**
 * The two agent settings the console shows but will not edit (design D6).
 *
 * A `class_path` typo stops the service booting, needs a restart anyway, and is
 * imported into the live process at *preview* time (§3.5). Both always address
 * the **global** table: the router table is built once at startup from the
 * global agents, so a per-project `endpoint_path` would be a value that never
 * takes effect.
 */
export function AGENT_READONLY_FIELDS(agentKey: string): FieldSpec[] {
  return [
    {
      key: agentPath(agentKey, 'endpoint_path'),
      type: 'text',
      hint: 'Edit in config.toml — changing it needs a service restart',
    },
    {
      key: agentPath(agentKey, 'class_path'),
      type: 'text',
      hint: 'Edit in config.toml — the class ships with the service, and a change needs a restart',
    },
  ]
}

/**
 * A project's own settings, other than its agent overrides.
 *
 * Language only (design D8). A project's `llm_config` is rendered read-only by
 * the Projects screen instead: the model supports it, the source design's
 * screen does not offer it, and phase 3 follows the source design.
 */
export function PROJECT_FIELDS(project: string): FieldSpec[] {
  return [
    {
      key: projectPath(project, 'language'),
      type: 'select',
      options: LANGUAGES,
      hint: 'Language used to resolve this project’s prompt files',
    },
  ]
}

/** Which control a declared `value_type` gets. */
const VAR_TYPES: Record<PromptVarDefinition['value_type'], FieldSpec['type']> = {
  string: 'text',
  text: 'textarea',
  boolean: 'bool',
  number: 'number',
  enum: 'select',
}

/**
 * One prompt variable, as the control its declaration calls for.
 *
 * The declaration is the prompt YAML's, not the config's: `value_type`,
 * `choices`, `name` and `description` all live per variant inside the prompt
 * file, which is exactly why the metadata endpoint exists (design D7). Without
 * it this would be an untyped key/value grid.
 */
export function promptVarField(
  scope: Scope,
  agentKey: string,
  varName: string,
  definition: PromptVarDefinition,
): FieldSpec {
  const prefix =
    scope.kind === 'global'
      ? ['agents', agentKey]
      : ['projects', scope.project, 'agents', agentKey]

  const hints = [definition.description, definition.required ? 'Required' : null].filter(
    (part): part is string => !!part,
  )

  return {
    key: joinPath([...prefix, 'prompt', 'vars', varName]),
    type: VAR_TYPES[definition.value_type] ?? 'text',
    // The declared name, not the path's last segment: `max_findings` is the
    // key, "Maximum findings" is what the prompt author called it.
    label: definition.name || varName,
    hint: hints.join(' · '),
    // An enum with no choices is invalid per the prompt schema, but this
    // renders whatever a file actually contains -- an empty select beats a
    // crashed screen on a config the operator can still fix.
    options: definition.value_type === 'enum' ? (definition.choices ?? []) : undefined,
  }
}

/**
 * What an unset variable falls back to — the prompt's declared default.
 *
 * `null` and absent are the same thing here: `PromptVariableDefinition`
 * defaults `default_value` to `None`, so a prompt that declares no default
 * arrives as `null`, which is "nothing to inherit" rather than "inherits
 * null".
 */
export function varDefault(definition: PromptVarDefinition): unknown {
  return definition.default_value ?? undefined
}
