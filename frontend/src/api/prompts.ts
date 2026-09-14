import type { Scope } from './agents'
import { apiFetch } from './client'
import type {
  MessageRole,
  PromptMessageDoc,
  PromptTestResult,
  PromptVariantDoc,
} from './types'

/** A new message. Inline until the operator moves it into a file of its own. */
export function emptyMessage(role: PromptMessageDoc['role'] = 'user'): PromptMessageDoc {
  return { role, source: 'inline', file: null, content: '', readable: true }
}

export function emptyVariant(name: string): PromptVariantDoc {
  return { name, description: null, model: null, vars: {}, messages: [emptyMessage()] }
}

/**
 * The one template suffix a message file is ever generated with.
 *
 * Shared with `promptDraft.ts`'s inline->file dedupe logic, which strips and
 * re-appends this same suffix when suffixing a colliding generated name --
 * the two must agree, or a generated name the dedupe logic doesn't recognise
 * as "already carrying the suffix" gets it appended twice.
 */
export const TEMPLATE_EXTENSION = '.jinja'

/**
 * The file name proposed when a message moves out of the YAML.
 *
 * `<variant-slug>_<role>.jinja` is not invented: it is the convention all eight
 * prompts this service ships already follow (`detailed_explanation_system.jinja`,
 * `kompakte_pruefung_user.jinja`). The operator can still change it; the server
 * validates whatever arrives.
 */
export function defaultTemplateName(variant: string, role: MessageRole): string {
  const slug =
    variant
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '_')
      .replace(/^_+|_+$/g, '') || 'variant'
  return `${slug}_${role}${TEMPLATE_EXTENSION}`
}

/**
 * Run a draft's messages against a real model.
 *
 * Split out from `useTestPrompt` (mutations.ts) the same way `fetchModels`
 * is split out of `useModels` -- the mutation hook is the thin, cached
 * wrapper; this is the actual request.
 */
export function testPrompt(body: {
  messages: PromptMessageDoc[]
  vars: Record<string, unknown>
  agent_context: Record<string, unknown>
  model: string
  project: string | null
}): Promise<PromptTestResult> {
  return apiFetch<PromptTestResult>('/prompts/test', {
    method: 'POST',
    body: JSON.stringify(body),
  })
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
