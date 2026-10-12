"""Tokenizer for the console's dotted edit paths.

An edit path addresses one key in the configuration document: ``port``,
``logging.file.log_level``, ``projects."Release 2.0".agents.reviewer.enabled``.

Splitting on ``.`` is not good enough, because a segment can be a TestBench
project name, and those are arbitrary strings -- ``docs/configuration.md``
says so explicitly ("including spaces and special characters"). A project
called ``Release 2.0`` produces a path that a naive split mis-addresses.

The grammar is deliberately the smallest one that fixes that, so every path
phase 2 produces still round-trips unquoted and stored drafts survive:

- a **bare** segment is any run of characters that contains no ``.``, ``"``,
  ``\\`` or NUL, and has no leading or trailing whitespace. Spaces and
  non-ASCII are fine -- neither is ambiguous;
- a **quoted** segment is ``"..."``, in which ``\\"`` means ``"`` and ``\\\\``
  means ``\\``. No other escape exists. Anything else may appear literally,
  including ``.`` and leading or trailing whitespace;
- an empty segment has no legal spelling in either form.

``join_path`` quotes a segment only when the bare form would not read back as
the same string, so it is a true inverse of ``split_path`` and the canonical
spelling of any path is stable.

This module is mirrored, grammar for grammar, by ``frontend/src/api/paths.ts``.
The two are pinned to one another by ``tests/fixtures/path_vectors.json``,
which both test suites consume. They must not be allowed to drift: if the
browser and the server disagree about what a path addresses, the browser
prunes an edit the server still applies, with no error anywhere.

Errors are ``ValueError``. Turning them into an HTTP status is the caller's
job -- ``webui/edits.py`` raises the 400.
"""

# Characters a bare segment may never contain. '.' is the delimiter; '"'
# introduces a quoted segment, so allowing it bare would make '"a"' ambiguous;
# '\' is the escape character; NUL has no business in a config key.
_BARE_FORBIDDEN = frozenset('."\\\x00')

# What counts as whitespace at a segment's edge, spelled out rather than left
# to ``str.strip()``. Python's default and JavaScript's ``trim()`` do not agree
# -- Python strips \x1c-\x1f and \x85, JavaScript strips the BOM -- so a segment
# ending in one of those would be quoted by one tokenizer and left bare by the
# other. That is exactly the silent divergence the shared vectors exist to
# prevent, so the set is the union of both and either side quotes it.
_EDGE_WHITESPACE = frozenset(
    " \t\n\v\f\r"
    "\x1c\x1d\x1e\x1f\x85"
    "\u00a0\u1680"
    "\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a"
    "\u2028\u2029\u202f\u205f\u3000\ufeff"
)


def _has_edge_whitespace(segment: str) -> bool:
    """Whether *segment* starts or ends with a character either side trims."""
    return bool(segment) and (segment[0] in _EDGE_WHITESPACE or segment[-1] in _EDGE_WHITESPACE)


def split_path(path: str) -> list[str]:
    """Split a dotted edit path into its segments.

    Raises:
        ValueError: the path is empty, has an empty segment, has an unquoted
            segment with leading or trailing whitespace or a forbidden
            character, has an unterminated quote, has an invalid escape, or has
            trailing junk after a closing quote.
    """
    if not path:
        raise ValueError("An edit path may not be empty")

    segments: list[str] = []
    index = 0
    length = len(path)

    while True:
        if index < length and path[index] == '"':
            segment, index = _read_quoted(path, index)
        else:
            segment, index = _read_bare(path, index)

        if not segment:
            raise ValueError(f"Edit path {path!r} has an empty segment")
        segments.append(segment)

        if index == length:
            return segments
        # _read_quoted and _read_bare both stop on '.' or end of string, so
        # this is the only possibility left.
        index += 1  # step over the delimiter
        if index == length:
            raise ValueError(f"Edit path {path!r} has an empty segment")


def _read_bare(path: str, start: int) -> tuple[str, int]:
    """Read an unquoted segment starting at *start*, stopping at '.' or end."""
    index = start
    while index < len(path) and path[index] != ".":
        char = path[index]
        if char in _BARE_FORBIDDEN:
            raise ValueError(
                f"Edit path {path!r} has an unquoted segment containing {char!r}; "
                'wrap the segment in double quotes, e.g. projects."a.b".language'
            )
        index += 1

    segment = path[start:index]
    if _has_edge_whitespace(segment):
        raise ValueError(
            f"Edit path {path!r} has a segment with leading or trailing whitespace; "
            "quote it if the whitespace is intentional"
        )
    return segment, index


def _read_quoted(path: str, start: int) -> tuple[str, int]:
    """Read a ``"..."`` segment whose opening quote is at *start*."""
    chars: list[str] = []
    index = start + 1
    length = len(path)

    while index < length:
        char = path[index]
        if char == '"':
            index += 1
            # A closing quote must end the segment: '"a"b' is not a segment.
            if index != length and path[index] != ".":
                raise ValueError(
                    f"Edit path {path!r} has characters after a closing quote; "
                    "a quoted segment must be followed by '.' or end there"
                )
            return "".join(chars), index
        if char == "\\":
            index += 1
            if index == length:
                raise ValueError(f"Edit path {path!r} ends with a dangling backslash")
            escaped = path[index]
            if escaped not in '"\\':
                raise ValueError(
                    f"Edit path {path!r} has an invalid escape '\\{escaped}'; "
                    'only \\" and \\\\ are recognised'
                )
            chars.append(escaped)
            index += 1
            continue
        if char == "\x00":
            raise ValueError(f"Edit path {path!r} may not contain a NUL byte")
        chars.append(char)
        index += 1

    raise ValueError(f"Edit path {path!r} has an unterminated quoted segment")


def join_path(segments: list[str]) -> str:
    """Render *segments* as a path that ``split_path`` reads back identically.

    Quotes a segment only when the bare form would not survive the round trip,
    so the canonical spelling of a path is stable and every path phase 2
    produced is rendered exactly as before.

    Raises:
        ValueError: no segments, an empty segment, or a segment containing NUL
            (which has no representable form in either spelling).
    """
    if not segments:
        raise ValueError("An edit path needs at least one segment")

    rendered: list[str] = []
    for segment in segments:
        if not segment:
            raise ValueError("An edit path segment may not be empty")
        if "\x00" in segment:
            raise ValueError("An edit path segment may not contain a NUL byte")
        rendered.append(_render_segment(segment))
    return ".".join(rendered)


def _render_segment(segment: str) -> str:
    needs_quotes = any(char in _BARE_FORBIDDEN for char in segment) or _has_edge_whitespace(segment)
    if not needs_quotes:
        return segment
    escaped = segment.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
