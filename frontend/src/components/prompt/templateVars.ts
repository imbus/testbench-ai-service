/**
 * Which `agent.*` / `vars.*` names a template references.
 *
 * A HINT for the variable sidebar's "used" dots and the undeclared warning --
 * never a validation. The server's real Jinja parse (lint, render) stays the
 * authority; a regex cannot see `{% set %}` aliases or attribute chains, and
 * that is acceptable for a hint.
 */
const TAG = /\{\{([\s\S]*?)\}\}|\{%([\s\S]*?)%\}/g
const NAME = /\b(agent|vars)\.([A-Za-z_]\w*)/g

export function usedTemplateVars(text: string): string[] {
  const seen: string[] = []
  for (const tag of text.matchAll(TAG)) {
    const body = tag[1] ?? tag[2] ?? ''
    for (const name of body.matchAll(NAME)) {
      const full = `${name[1]}.${name[2]}`
      if (!seen.includes(full)) seen.push(full)
    }
  }
  return seen
}

/** Bare keys of every `vars.*` reference the variant does not declare. */
export function undeclaredVars(used: string[], declaredKeys: string[]): string[] {
  return used
    .filter((name) => name.startsWith('vars.'))
    .map((name) => name.slice('vars.'.length))
    .filter((key) => !declaredKeys.includes(key))
}
