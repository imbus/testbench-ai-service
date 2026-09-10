"""The console's edit overlay.

The browser does not post a whole configuration document back. It posts a
sparse map of dotted paths to new values, which the server merges into the
config it reads *fresh off disk* at preview and apply time. Three reasons:

- ``GET /config`` redacts credential-named values, so a whole-config round trip
  would write the literal string ``***REDACTED***`` into the file;
- the ``running`` snapshot is fully defaulted, so writing it back would expand a
  five-line hand-written ``config.toml`` into every default the model has;
- merging into a freshly-read disk config means a second operator's diff shows
  the first operator's changes rather than silently reverting them.

Everything here is a pure function over plain dicts. No TOML, no filesystem, no
request objects -- which is what makes it the right place to enforce the
sentinel and path rules once, for both preview and apply.
"""

from typing import Any, cast

from fastapi import HTTPException, status

from testbench_ai_service.webui.config_io import REDACTED_SENTINEL
from testbench_ai_service.webui.paths import join_path, split_path

ConfigEdits = dict[str, Any]

# Bounds, not policy: they exist so a malformed or hostile payload cannot make
# the server walk an unbounded structure. The real config is nowhere near
# either limit -- the deepest legitimate path is
# 'projects."<name>".agents.<key>.prompt.vars.<var>' at seven segments.
MAX_EDITS = 500
MAX_PATH_SEGMENTS = 8


def _reject(detail: str) -> None:
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


def _contains_sentinel(value: Any) -> bool:
    """True if *value* holds the redaction sentinel anywhere inside it."""
    if isinstance(value, str):
        return value == REDACTED_SENTINEL
    if isinstance(value, dict):
        return any(_contains_sentinel(item) for item in value.values())
    if isinstance(value, (list, tuple, set, frozenset)):
        return any(_contains_sentinel(item) for item in value)
    return False


def _check_path_prefix_collisions(tokenized: dict[str, list[str]]) -> None:
    """Reject overlays with both a path and a proper prefix of that path.

    Compares *segments*, not strings. Two spellings of the same path -- say
    ``projects."My Project"`` and ``projects.My Project`` -- are the same
    address, and a string-prefix test would miss the collision between them.
    """
    by_segments = {tuple(segments): path for path, segments in tokenized.items()}
    for path, segments in tokenized.items():
        for index in range(1, len(segments)):
            prefix = tuple(segments[:index])
            if prefix in by_segments:
                _reject(
                    f"Edit paths {path!r} and {by_segments[prefix]!r} conflict: "
                    "send one value for the table, not separate entries"
                )


def _tokenize(path: str) -> list[str]:
    """Split *path* into segments, turning a malformed path into a 400."""
    try:
        return split_path(path)
    except ValueError as e:
        _reject(str(e))
        raise  # unreachable; _reject always raises


def _validate_single_path(path: str, value: Any) -> list[str]:
    """Validate a single path and its value, returning its segments."""
    if not isinstance(path, str) or not path.strip():
        _reject("An edit path must be a non-empty string")
    segments = _tokenize(path)
    if len(segments) > MAX_PATH_SEGMENTS:
        _reject(f"Edit path {path!r} is nested deeper than {MAX_PATH_SEGMENTS} levels")
    if _contains_sentinel(value):
        # The console shows credential-named values as REDACTED_SENTINEL.
        # Writing that string back would replace a real secret with a
        # placeholder, or plant the placeholder as a value. Neither is ever
        # what the operator meant.
        _reject(
            f"Edit path {path!r} carries the redacted placeholder. "
            "Credential values cannot be set from the console."
        )
    return segments


def validate_edit_paths(edits: ConfigEdits) -> None:
    """Check every path and value in *edits* before anything acts on them.

    Raises:
        HTTPException 400: too many edits, a malformed dotted path, or a value
            that is (or contains) the redaction sentinel.
    """
    if len(edits) > MAX_EDITS:
        _reject(f"Too many edits in one request (limit {MAX_EDITS})")

    # Per-path validation runs first: the collision check tokenizes every path,
    # which is only meaningful once each one is known to be well formed.
    tokenized = {path: _validate_single_path(path, value) for path, value in edits.items()}

    _check_path_prefix_collisions(tokenized)


def merge_edits(base: dict[str, Any], edits: ConfigEdits) -> dict[str, Any]:
    """Return a deep copy of *base* with *edits* applied.

    A ``None`` value removes the key, so the model default takes over again.
    Removing an absent key is a no-op, not an error: two operators can discard
    the same setting without the second one getting a 400.

    *base* is never mutated -- the caller still needs it to diff against.
    """
    merged = cast(dict[str, Any], _deep_copy(base))
    for path, value in edits.items():
        segments = _tokenize(path)
        if value is None:
            _remove_at(merged, segments)
        else:
            _set_at(merged, segments, value)
    return merged


def _deep_copy(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _deep_copy(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_deep_copy(item) for item in value]
    return value


def _set_at(target: dict[str, Any], segments: list[str], value: Any) -> None:
    node = target
    for segment in segments[:-1]:
        child = node.get(segment)
        if child is None:
            child = {}
            node[segment] = child
        elif not isinstance(child, dict):
            path = join_path(segments)
            _reject(f"Edit path {path!r} conflicts with {segment!r}, which is not a table")
        node = child
    node[segments[-1]] = _deep_copy(value)


def _remove_at(target: dict[str, Any], segments: list[str]) -> None:
    node: Any = target
    for segment in segments[:-1]:
        if not isinstance(node, dict) or segment not in node:
            return
        node = node[segment]
    if isinstance(node, dict):
        node.pop(segments[-1], None)
