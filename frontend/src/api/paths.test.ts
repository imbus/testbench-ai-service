import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, test } from 'vitest'
import { joinPath, lastSegment, splitPath } from './paths'

/**
 * The same fixture `tests/unit/webui/test_paths.py` consumes.
 *
 * These two tokenizers must agree exactly. If they drift, `prune` in
 * state/draft.tsx and `merge_edits` in webui/edits.py disagree about what a
 * path addresses, and the browser silently drops an edit the server still
 * applies. Change the fixture, never one side's expectations.
 */
// Resolved from this file rather than from cwd, so the suite works whether it
// is started in frontend/ or at the repo root. `new URL(relative,
// import.meta.url)` is not usable here: Vite rewrites it into an /admin/@fs/
// app URL that readFileSync cannot open.
const FIXTURE = resolve(
  dirname(fileURLToPath(import.meta.url)),
  '../../../tests/fixtures/path_vectors.json',
)

const vectors = JSON.parse(readFileSync(FIXTURE, 'utf-8')) as {
  roundtrip: { path: string; segments: string[] }[]
  split_only: { path: string; segments: string[]; joins_to: string }[]
  invalid: string[]
}

describe('shared vectors', () => {
  test('the fixture is not empty', () => {
    // A silently empty fixture would make every case below vacuous.
    expect(vectors.roundtrip.length).toBeGreaterThanOrEqual(10)
    expect(vectors.invalid.length).toBeGreaterThanOrEqual(10)
  })

  test.each(vectors.roundtrip)('splits $path', ({ path, segments }) => {
    expect(splitPath(path)).toEqual(segments)
  })

  test.each(vectors.roundtrip)('joins back to $path', ({ path, segments }) => {
    expect(joinPath(segments)).toBe(path)
  })

  test.each(vectors.split_only)('splits the non-canonical $path', ({ path, segments }) => {
    expect(splitPath(path)).toEqual(segments)
  })

  test.each(vectors.split_only)('canonicalises $path', ({ segments, joins_to }) => {
    expect(joinPath(segments)).toBe(joins_to)
  })

  test.each(vectors.invalid.map((path) => ({ path })))('rejects $path', ({ path }) => {
    expect(() => splitPath(path)).toThrow()
  })
})

describe('joinPath guards', () => {
  test('refuses an empty segment list', () => {
    expect(() => joinPath([])).toThrow()
  })

  test('refuses an empty segment', () => {
    // There is no spelling of an empty segment that splitPath accepts back.
    expect(() => joinPath(['projects', '', 'language'])).toThrow()
  })
})

describe('lastSegment', () => {
  test('returns the final segment of a plain path', () => {
    expect(lastSegment('llm_config.model')).toBe('model')
  })

  test('unquotes the final segment', () => {
    expect(lastSegment('projects."Release 2.0"')).toBe('Release 2.0')
  })

  test('returns the whole path for a single segment', () => {
    expect(lastSegment('port')).toBe('port')
  })

  test('falls back to the raw path rather than throwing', () => {
    // Field specs are built with joinPath so this should be unreachable, but a
    // label is not worth crashing a render over.
    expect(lastSegment('projects."unterminated')).toBe('projects."unterminated')
  })
})
