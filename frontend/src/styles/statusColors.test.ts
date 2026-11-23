import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

// Read from disk: vitest stubs CSS modules, even with `?raw`, and under jsdom
// import.meta.url is not a file URL. Vitest runs from frontend/.
const industry = readFileSync(resolve(process.cwd(), 'src/styles/industry.css'), 'utf-8')

/**
 * Status colors come from theme tokens, never from literals in components: a
 * literal does not follow the dark theme, and the old dark reds fell below
 * WCAG AA on the dark surface.
 */

const sources = import.meta.glob(['../**/*.tsx', '!../**/*.test.tsx'], {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>

const HEX = /#[0-9a-fA-F]{3,8}\b/g

describe('status colors', () => {
  it('scans the component sources', () => {
    // Guards the glob itself: an empty match would make the next test vacuous.
    expect(Object.keys(sources).length).toBeGreaterThan(20)
  })

  it('has no hex color literals in components', () => {
    const offenders = Object.entries(sources).flatMap(([file, text]) =>
      text.split('\n').flatMap((line, i) =>
        // Inside a string or a style value, not an HTML entity or a URL fragment.
        [...line.matchAll(HEX)]
          .filter((match) => /['"`(\s:,]/.test(line[match.index - 1] ?? ''))
          .map((match) => `${file}:${i + 1} ${match[0]}`),
      ),
    )
    expect(offenders, 'use var(--color-success|warning|danger|muted) instead').toEqual([])
  })

  const TOKENS = ['success', 'warning', 'danger'].flatMap((name) => [
    `--color-${name}`,
    `--color-${name}-soft`,
  ])

  it.each(TOKENS)('defines %s for the light theme', (token) => {
    const root = industry.slice(
      industry.indexOf(':root {'),
      industry.indexOf('}', industry.indexOf(':root {')),
    )
    expect(root).toContain(`${token}:`)
  })

  it.each(TOKENS.filter((token) => !token.endsWith('-soft')))(
    'redefines %s for the dark theme',
    (token) => {
      // Quoted or not: Prettier writes the attribute value quoted.
      const start = industry.search(/\[data-theme=['"]?dark['"]?\] \{/)
      expect(start, 'a [data-theme=dark] { … } token block').toBeGreaterThan(-1)
      expect(industry.slice(start, industry.indexOf('}', start))).toContain(`${token}:`)
    },
  )
})
