"""Unified diffs for the console's apply dialog.

The diff is what the operator actually approves, so it is computed against the
file as it is on disk at that moment -- not against whatever the browser
happened to load earlier. Two operators editing at once therefore see each
other's changes in the diff instead of silently reverting them.
"""

import difflib

from testbench_ai_service.webui.models import FileDiff

# Enough context to recognise which part of the file a change lands in, without
# turning a one-key edit into a diff of the whole file.
CONTEXT_LINES = 3


def file_diff(path: str, current: str, proposed: str) -> FileDiff | None:
    """Diff *current* against *proposed*.

    Returns:
        A :class:`FileDiff`, or ``None`` when the two texts are identical --
        which is how the caller decides a file needs no write at all.
    """
    if current == proposed:
        return None

    lines = list(
        difflib.unified_diff(
            current.splitlines(keepends=True),
            proposed.splitlines(keepends=True),
            fromfile=path,
            tofile=path,
            n=CONTEXT_LINES,
        )
    )

    # The first two lines are the '---'/'+++' file headers, which start with the
    # same characters as real changes. Counting skips them by position rather
    # than by a longer prefix test: a genuine removed line reading '--- note'
    # is perfectly possible in a commented TOML file.
    body = lines[2:]
    added = sum(1 for line in body if line.startswith("+"))
    removed = sum(1 for line in body if line.startswith("-"))

    return FileDiff(path=path, diff="".join(lines), added=added, removed=removed)
