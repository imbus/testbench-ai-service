import type { PromptVarDecl } from '../../api/types'
import { sampleType } from './VarSidebar'

/**
 * What the template editor suggests at the cursor.
 *
 * Kept free of Monaco so it is testable under jsdom: `CodeEditor` maps the
 * items onto Monaco's own completion type. Like `templateVars.ts`, this is a
 * HINT -- a scan of the text before the cursor, not a Jinja parse. The roots
 * are exactly the two the server renders with (`agent`, `vars`), so a name
 * this offers is one the preview can resolve.
 */
export type CompletionContext = {
  /** The merged agent sample/skeleton, as `agentContextOf` builds it. */
  agent: Record<string, unknown>
  /** The selected variant's own declarations. */
  vars: Record<string, PromptVarDecl>
}

export type TemplateCompletion = {
  label: string
  kind: 'root' | 'field' | 'variable' | 'keyword'
  detail?: string
  documentation?: string
}

export type TemplateCompletions = {
  items: TemplateCompletion[]
  /** How many characters before the cursor the chosen item replaces. */
  replaceLength: number
}

const ROOTS: TemplateCompletion[] = [
  { label: 'agent', kind: 'root', detail: 'agent context' },
  { label: 'vars', kind: 'root', detail: 'variant variables' },
]

const KEYWORDS = [
  'if', 'elif', 'else', 'endif', 'for', 'endfor', 'set', 'endset',
  'macro', 'endmacro', 'filter', 'endfilter', 'raw', 'endraw', 'with', 'endwith',
]

const OPENERS = ['{{', '{%', '{#'] as const
const CLOSERS = { '{{': '}}', '{%': '%}', '{#': '#}' } as const

/** The tag the cursor sits in and the text typed inside it so far, or null outside any tag. */
function openTag(text: string): { opener: (typeof OPENERS)[number]; body: string } | null {
  let best: { opener: (typeof OPENERS)[number]; at: number } | null = null
  for (const opener of OPENERS) {
    const at = text.lastIndexOf(opener)
    if (at >= 0 && (!best || at > best.at)) best = { opener, at }
  }
  if (!best) return null
  const body = text.slice(best.at + 2)
  if (body.includes(CLOSERS[best.opener])) return null
  return { opener: best.opener, body }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/** The agent sample node a dotted path names, or undefined once it leaves plain objects. */
function agentNode(agent: Record<string, unknown>, path: string[]): Record<string, unknown> | undefined {
  let node: unknown = agent
  for (const segment of path) {
    if (!isRecord(node) || !(segment in node)) return undefined
    node = node[segment]
  }
  // A dict sample (`{'<key>': …}`) or a list is reached by subscript or a
  // `{% for %}` loop, never by a further attribute.
  if (!isRecord(node) || '<key>' in node) return undefined
  return node
}

function varDocumentation(decl: PromptVarDecl): string | undefined {
  const parts: string[] = []
  if (decl.description) parts.push(decl.description)
  if (decl.choices?.length) parts.push(`Choices: ${decl.choices.join(', ')}`)
  if (decl.default_value !== null && decl.default_value !== undefined && decl.default_value !== '') {
    parts.push(`Default: ${String(decl.default_value)}`)
  }
  return parts.length ? parts.join('\n\n') : undefined
}

// A dotted chain at the very end of the text, with whatever precedes it.
const CHAIN = /(^|[^\w.\])])((?:[A-Za-z_]\w*\.)*)([A-Za-z_]\w*)?$/

/** Completions for the cursor at the end of *textBefore*, or null when nothing applies. */
export function templateCompletions(textBefore: string, ctx: CompletionContext): TemplateCompletions | null {
  const tag = openTag(textBefore)
  if (!tag || tag.opener === '{#') return null

  const match = CHAIN.exec(tag.body)
  if (!match) return null
  const path = match[2] ? match[2].slice(0, -1).split('.') : []
  const partial = match[3] ?? ''
  const replaceLength = partial.length

  if (path.length === 0) {
    // The first word of a block tag is its statement keyword.
    const statementStart = tag.opener === '{%' && /^[-+]?\s*$/.test(tag.body.slice(0, tag.body.length - partial.length))
    if (statementStart) {
      return { items: KEYWORDS.map((label) => ({ label, kind: 'keyword' })), replaceLength }
    }
    return { items: ROOTS, replaceLength }
  }

  const [root, ...rest] = path
  if (root === 'agent') {
    const node = agentNode(ctx.agent, rest)
    if (!node) return null
    const items = Object.entries(node).map(([label, value]): TemplateCompletion => ({
      label,
      kind: 'field',
      detail: sampleType(value),
    }))
    return items.length ? { items, replaceLength } : null
  }
  if (root === 'vars' && rest.length === 0) {
    const items = Object.entries(ctx.vars).map(([label, decl]): TemplateCompletion => ({
      label,
      kind: 'variable',
      detail: decl.value_type,
      documentation: varDocumentation(decl),
    }))
    return items.length ? { items, replaceLength } : null
  }
  return null
}
