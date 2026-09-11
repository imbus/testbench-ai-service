import type { Scope } from './agents'
import type { PromptMessageDoc, PromptVariantDoc } from './types'

/** A new message. Always inline: phase 4a never creates a template file. */
export function emptyMessage(role: PromptMessageDoc['role'] = 'user'): PromptMessageDoc {
  return { role, source: 'inline', file: null, content: '', readable: true }
}

export function emptyVariant(name: string): PromptVariantDoc {
  return { name, description: null, model: null, vars: {}, messages: [emptyMessage()] }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/**
 * Reconcile the server's context skeleton with what the operator has typed.
 *
 * The skeleton is authoritative about which keys exist -- it comes from the
 * real Jinja AST -- and the operator's values win wherever a key survives.
 */
export function mergeContext(
  skeleton: Record<string, unknown>,
  current: Record<string, unknown>,
): Record<string, unknown> {
  const merged: Record<string, unknown> = {}
  for (const [key, shape] of Object.entries(skeleton)) {
    const existing = current?.[key]
    if (isRecord(shape)) {
      merged[key] = mergeContext(shape, isRecord(existing) ? existing : {})
    } else {
      merged[key] = existing === undefined ? shape : existing
    }
  }
  return merged
}

function variantOf(block: unknown): string | null {
  if (!isRecord(block)) return null
  const prompt = block.prompt
  if (!isRecord(prompt)) return null
  const variant = prompt.variant
  return typeof variant === 'string' && variant.trim() ? variant : null
}

/**
 * Which config keys name *variant* for *agentKey*, as structured scopes.
 *
 * The client-side mirror of the server's guard, so the editor can warn before
 * a save is refused with a 409. `disk` is unvalidated TOML: a bad shape must
 * cost a check, not a render.
 *
 * Returns `Scope`s rather than pre-built English labels -- the operator-facing
 * console defaults to German, so a caller must be able to localize "the
 * global agents table" / "project 'X'" through `useTranslations`, the same as
 * every other piece of console prose. Only the project NAME (a wire token,
 * like an agent key) survives untranslated.
 */
export function agentsUsingVariant(
  disk: Record<string, unknown>,
  agentKey: string,
  variant: string,
): Scope[] {
  const refs: Scope[] = []

  const agents = disk?.agents
  if (isRecord(agents) && variantOf(agents[agentKey]) === variant) {
    refs.push({ kind: 'global' })
  }

  const projects = disk?.projects
  if (isRecord(projects)) {
    for (const [name, block] of Object.entries(projects)) {
      if (!isRecord(block)) continue
      const projectAgents = block.agents
      if (!isRecord(projectAgents)) continue
      if (variantOf(projectAgents[agentKey]) === variant) refs.push({ kind: 'project', project: name })
    }
  }

  return refs
}
