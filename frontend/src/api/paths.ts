/**
 * Tokenizer for the console's dotted edit paths.
 *
 * An edit path addresses one key in the configuration document: `port`,
 * `logging.file.log_level`, `projects."Release 2.0".agents.reviewer.enabled`.
 *
 * Splitting on `.` is not good enough, because a segment can be a TestBench
 * project name, and those are arbitrary strings — `docs/configuration.md` says
 * so explicitly ("including spaces and special characters"). A project called
 * `Release 2.0` produces a path that a naive split mis-addresses.
 *
 * The grammar is deliberately the smallest one that fixes that, so every path
 * phase 2 produces still round-trips unquoted and stored drafts survive:
 *
 * - a **bare** segment is any run of characters that contains no `.`, `"`,
 *   `\` or NUL, and has no leading or trailing whitespace. Spaces and
 *   non-ASCII are fine — neither is ambiguous;
 * - a **quoted** segment is `"..."`, in which `\"` means `"` and `\\` means
 *   `\`. No other escape exists. Anything else may appear literally, including
 *   `.` and leading or trailing whitespace;
 * - an empty segment has no legal spelling in either form.
 *
 * `joinPath` quotes a segment only when the bare form would not read back as
 * the same string, so it is a true inverse of `splitPath`.
 *
 * This module mirrors, grammar for grammar, `testbench_ai_service/webui/paths.py`.
 * The two are pinned to one another by `tests/fixtures/path_vectors.json`,
 * which both test suites consume. They must not be allowed to drift: if the
 * browser and the server disagree about what a path addresses, the browser
 * prunes an edit the server still applies, with no error anywhere.
 */

/**
 * Characters a bare segment may never contain. `.` is the delimiter; `"`
 * introduces a quoted segment, so allowing it bare would make `"a"` ambiguous;
 * `\` is the escape character; NUL has no business in a config key.
 */
const BARE_FORBIDDEN = new Set(['.', '"', '\\', '\0'])

/**
 * What counts as whitespace at a segment's edge, spelled out rather than
 * left to `trim()`.
 *
 * `String.prototype.trim()` and Python's `str.strip()` do not agree --
 * Python strips \x1c-\x1f and \x85, JavaScript strips the BOM -- so
 * a segment ending in one of those would be quoted by one tokenizer and
 * left bare by the other. The set is the union of both, so either side
 * quotes it, and `tests/fixtures/path_vectors.json` carries a case for each.
 */
const EDGE_WHITESPACE = new Set(
  ' \t\n\v\f\r' +
    '\x1c\x1d\x1e\x1f\x85' +
    '\xa0\u1680' +
    '\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a' +
    '\u2028\u2029\u202f\u205f\u3000\ufeff',
)

function hasEdgeWhitespace(segment: string): boolean {
  return (
    segment.length > 0 &&
    (EDGE_WHITESPACE.has(segment[0]) || EDGE_WHITESPACE.has(segment[segment.length - 1]))
  )
}

/**
 * Split a dotted edit path into its segments.
 *
 * @throws if the path is empty, has an empty segment, has an unquoted segment
 * with leading/trailing whitespace or a forbidden character, has an
 * unterminated quote, has an invalid escape, or has junk after a closing quote.
 */
export function splitPath(path: string): string[] {
  if (!path) throw new Error('An edit path may not be empty')

  const segments: string[] = []
  let index = 0

  for (;;) {
    let segment: string
    if (index < path.length && path[index] === '"') {
      ;[segment, index] = readQuoted(path, index)
    } else {
      ;[segment, index] = readBare(path, index)
    }

    if (!segment) throw new Error(`Edit path ${JSON.stringify(path)} has an empty segment`)
    segments.push(segment)

    if (index === path.length) return segments
    // readQuoted and readBare both stop on '.' or end of string, so this is
    // the only possibility left.
    index += 1 // step over the delimiter
    if (index === path.length) {
      throw new Error(`Edit path ${JSON.stringify(path)} has an empty segment`)
    }
  }
}

/** Read an unquoted segment starting at `start`, stopping at '.' or end. */
function readBare(path: string, start: number): [string, number] {
  let index = start
  while (index < path.length && path[index] !== '.') {
    const char = path[index]
    if (BARE_FORBIDDEN.has(char)) {
      throw new Error(
        `Edit path ${JSON.stringify(path)} has an unquoted segment containing ${JSON.stringify(char)}; ` +
          'wrap the segment in double quotes, e.g. projects."a.b".language',
      )
    }
    index += 1
  }

  const segment = path.slice(start, index)
  if (hasEdgeWhitespace(segment)) {
    throw new Error(
      `Edit path ${JSON.stringify(path)} has a segment with leading or trailing whitespace; ` +
        'quote it if the whitespace is intentional',
    )
  }
  return [segment, index]
}

/** Read a `"..."` segment whose opening quote is at `start`. */
function readQuoted(path: string, start: number): [string, number] {
  const chars: string[] = []
  let index = start + 1

  while (index < path.length) {
    const char = path[index]
    if (char === '"') {
      index += 1
      // A closing quote must end the segment: '"a"b' is not a segment.
      if (index !== path.length && path[index] !== '.') {
        throw new Error(
          `Edit path ${JSON.stringify(path)} has characters after a closing quote; ` +
            "a quoted segment must be followed by '.' or end there",
        )
      }
      return [chars.join(''), index]
    }
    if (char === '\\') {
      index += 1
      if (index === path.length) {
        throw new Error(`Edit path ${JSON.stringify(path)} ends with a dangling backslash`)
      }
      const escaped = path[index]
      if (escaped !== '"' && escaped !== '\\') {
        throw new Error(
          `Edit path ${JSON.stringify(path)} has an invalid escape '\\${escaped}'; ` +
            'only \\" and \\\\ are recognised',
        )
      }
      chars.push(escaped)
      index += 1
      continue
    }
    if (char === '\0') {
      throw new Error(`Edit path ${JSON.stringify(path)} may not contain a NUL byte`)
    }
    chars.push(char)
    index += 1
  }

  throw new Error(`Edit path ${JSON.stringify(path)} has an unterminated quoted segment`)
}

/**
 * Render `segments` as a path that `splitPath` reads back identically.
 *
 * Quotes a segment only when the bare form would not survive the round trip,
 * so the canonical spelling of a path is stable and every path phase 2
 * produced is rendered exactly as before.
 *
 * @throws if there are no segments, a segment is empty, or a segment contains
 * NUL (which has no representable form in either spelling).
 */
export function joinPath(segments: string[]): string {
  if (segments.length === 0) throw new Error('An edit path needs at least one segment')

  return segments
    .map((segment) => {
      if (!segment) throw new Error('An edit path segment may not be empty')
      if (segment.includes('\0')) {
        throw new Error('An edit path segment may not contain a NUL byte')
      }
      return renderSegment(segment)
    })
    .join('.')
}

/**
 * The final segment of a path, unquoted — what a field label shows.
 *
 * Falls back to the raw path if it cannot be parsed. Field specs are built
 * with `joinPath`, so that should be unreachable; a label is not worth
 * crashing a render over.
 */
export function lastSegment(path: string): string {
  try {
    const segments = splitPath(path)
    return segments[segments.length - 1]
  } catch {
    return path
  }
}

function renderSegment(segment: string): string {
  const needsQuotes =
    [...segment].some((char) => BARE_FORBIDDEN.has(char)) || hasEdgeWhitespace(segment)
  if (!needsQuotes) return segment
  return `"${segment.replace(/\\/g, '\\\\').replace(/"/g, '\\"')}"`
}
