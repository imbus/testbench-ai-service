/**
 * The inherit/override model behind the Agents and Projects screens.
 *
 * `config.toml` holds a global `[agents.<key>]` table plus, per project, a
 * *sparse* `[projects."<name>".agents.<key>]` override. Three states matter and
 * must stay distinguishable everywhere:
 *
 * - **inherit** — the project says nothing, and the global value applies;
 * - **override** — the project says something, and it wins;
 * - **remove** — a queued `null` edit, which the server reads as "delete the
 *   key", i.e. "go back to inheriting".
 *
 * A project that says nothing is not a project that says `false`. Collapsing
 * the two would make "this project has an opinion" unrepresentable, and the
 * operator could never take an override back off.
 *
 * Every path is built with `joinPath`, never by string concatenation: project
 * blocks are keyed by the raw TestBench project name, which may contain dots
 * (`Release 2.0`) or quotes. A hand-built path for such a name addresses
 * nothing the server recognises — silently.
 */
import { joinPath } from './paths'

/** One agent's settings, as `config.toml` spells them. */
export interface AgentSettings {
  enabled?: unknown
  endpoint_path?: unknown
  class_path?: unknown
  prompt?: Record<string, unknown>
}

/** Which agent, in which scope, a screen is currently editing. */
export type Scope = { kind: 'global' } | { kind: 'project'; project: string }

function table(node: unknown): Record<string, unknown> | undefined {
  // `disk` is unvalidated TOML, so every level can be the wrong type. An
  // unexpected shape costs the operator a row, never a crashed render on a
  // config they could still fix from the Raw screen.
  return node !== null && typeof node === 'object' && !Array.isArray(node)
    ? (node as Record<string, unknown>)
    : undefined
}

/** Address a setting on the global `[agents.<key>]` table. */
export function agentPath(agentKey: string, setting?: string): string {
  const tail = setting ? setting.split('.') : []
  return joinPath(['agents', agentKey, ...tail])
}

/** Address a project's table, or a setting on it. */
export function projectPath(project: string, setting?: string): string {
  const tail = setting ? setting.split('.') : []
  return joinPath(['projects', project, ...tail])
}

/** Address a setting on a project's override of one agent. */
export function projectAgentPath(project: string, agentKey: string, setting?: string): string {
  const tail = setting ? setting.split('.') : []
  return joinPath(['projects', project, 'agents', agentKey, ...tail])
}

/** Address a setting for whichever scope is in play. */
export function scopedAgentPath(scope: Scope, agentKey: string, setting?: string): string {
  return scope.kind === 'global'
    ? agentPath(agentKey, setting)
    : projectAgentPath(scope.project, agentKey, setting)
}

function deepMerge(
  base: Record<string, unknown>,
  override: Record<string, unknown>,
): Record<string, unknown> {
  const merged: Record<string, unknown> = { ...base }
  for (const [key, value] of Object.entries(override)) {
    const existing = table(merged[key])
    const incoming = table(value)
    merged[key] = existing && incoming ? deepMerge(existing, incoming) : value
  }
  return merged
}

/**
 * One agent's settings as they apply in *project*, or globally when `null`.
 *
 * Mirrors the server's merge exactly: the project override is deep-merged onto
 * the global table, so `[projects.X.agents.y.prompt] variant = "..."` changes
 * the variant and keeps the prompt's `file`. Anything the project does not
 * mention is inherited, which is what makes "inherit" the default state of
 * every control on these screens.
 */
export function effectiveAgent(
  config: Record<string, unknown>,
  agentKey: string,
  project: string | null,
): AgentSettings {
  const global = table(table(config.agents)?.[agentKey]) ?? {}
  if (project === null) return global as AgentSettings

  const override = table(
    table(table(table(config.projects)?.[project])?.agents)?.[agentKey],
  )
  return (override ? deepMerge(global, override) : global) as AgentSettings
}

/**
 * The names of the projects that override *agentKey*, in config order.
 *
 * An empty override table counts: `[projects.Alpha.agents.x]` with nothing
 * under it is still a block the operator wrote, and hiding it would make the
 * Agents list disagree with the file.
 */
export function overridingProjects(
  config: Record<string, unknown>,
  agentKey: string,
): string[] {
  const projects = table(config.projects)
  if (!projects) return []
  return Object.keys(projects).filter(
    (name) => table(table(table(projects[name])?.agents)?.[agentKey]) !== undefined,
  )
}

/** Every agent key the config declares, in config order. */
export function agentKeys(config: Record<string, unknown>): string[] {
  return Object.keys(table(config.agents) ?? {})
}

/** Every project name the config declares a block for, in config order. */
export function configuredProjects(config: Record<string, unknown>): string[] {
  return Object.keys(table(config.projects) ?? {})
}
