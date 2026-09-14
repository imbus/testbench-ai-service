"""Multi-file replacement and deletion for the prompt editor's saves.

``atomic.write_atomic`` is single-file by construction, but saving one prompt
touches ``prompt.yaml`` plus every template file whose body changed.

This is **not** a journal and does not claim set-atomicity: ``os.replace`` is
atomic per file, and N files cannot be replaced as one operation. Instead, a
five-phase model minimizes vulnerability windows:

1. Stage every content to temp files (nothing is committed yet).
2. Back up all write targets that exist.
3. Back up all delete targets that exist (each becomes its ``.bak``; only copy).
4. Replace all write targets (the main state-mutation window).
5. Remove all delete targets (last, so a failure while writing never leaves
   a file already deleted).

A failure anywhere in phases 4-5 rolls back both delete and write operations
in reverse order: deletes are restored first (from their backups), then writes,
before raising an exception to the caller.
"""

import os
import tempfile
from collections.abc import Sequence
from pathlib import Path

from fastapi import HTTPException, status
from pydantic import BaseModel

from testbench_ai_service.log import logger


class MultiWriteResult(BaseModel):
    """What a completed :func:`write_all` did."""

    written: list[Path] = []
    #: The subset of *written* that did not exist before this call.
    created: list[Path] = []
    #: Targets removed. Each one's previous contents are in its ``.bak``.
    deleted: list[Path] = []
    #: target -> the ``.bak`` holding its previous contents. Absent for a file
    #: that did not exist before.
    backups: dict[Path, Path] = {}
    #: Targets restored after a mid-sequence failure. Only ever non-empty on
    #: the error path, which raises -- surfaced for the log, not for a caller.
    rolled_back: list[Path] = []


def _stage(target: Path, content: str | bytes) -> Path:
    """Write *content* to a temp file beside *target* and fsync it."""
    directory = target.parent
    if not directory.is_dir():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot write {target}: {directory} is not a directory",
        )
    handle, temp_name = tempfile.mkstemp(
        dir=str(directory), prefix=f".{target.name}.", suffix=".tmp"
    )
    if isinstance(content, bytes):
        # A byte copy is exactly that: no decode, no newline translation. This
        # is what lets a fork copy a latin-1 or CRLF template faithfully.
        with os.fdopen(handle, "wb") as binary:
            binary.write(content)
            binary.flush()
            os.fsync(binary.fileno())
        return Path(temp_name)
    # newline="" keeps the text exactly as rendered; the default would turn
    # every "\n" into "\r\n" on Windows and rewrite every line of the file.
    with os.fdopen(handle, "w", encoding="utf-8", newline="") as file:
        file.write(content)
        file.flush()
        os.fsync(file.fileno())
    return Path(temp_name)


def _backup_existing(paths: Sequence[Path], result: MultiWriteResult) -> None:
    """Back up any of *paths* that exist to a ``.bak`` in the same directory."""
    for target in paths:
        if target.exists():
            backup = target.with_name(f"{target.name}.bak")
            backup.write_bytes(target.read_bytes())
            result.backups[target] = backup


def write_all(files: dict[Path, str | bytes], deletes: Sequence[Path] = ()) -> MultiWriteResult:
    """Replace every target in *files*, then remove every path in *deletes*.

    Deletes run **last**, so a failure while writing can never leave a file
    already removed. A delete is a copy to ``<name>.bak`` followed by an
    unlink, matching ``config.toml.bak``: the backup exists so an operator can
    undo the last console save, not as a history, and it is overwritten rather
    than rotated.

    Raises:
        HTTPException 400: staging failed (nothing was replaced or removed), or
            a replace or unlink failed part-way (what had already been done is
            restored).
    """
    targets = sorted(files, key=str)
    doomed = sorted(set(deletes), key=str)
    if not targets and not doomed:
        return MultiWriteResult()

    staged: dict[Path, Path] = {}
    result = MultiWriteResult()

    try:
        # Phase 1 -- stage everything. No target has changed yet.
        for target in targets:
            staged[target] = _stage(target, files[target])

        # Phase 2 -- back up the write targets that exist.
        _backup_existing(targets, result)

        # Phase 3 -- back up the delete targets. Same operation, different
        # purpose: this backup is the only copy once the unlink lands.
        _backup_existing(doomed, result)

        # Phase 4 -- replace.
        for target in targets:
            existed = target in result.backups
            try:
                os.replace(staged[target], target)  # noqa: PTH105
            except OSError:
                _roll_back(result, target)
                raise
            staged.pop(target)
            result.written.append(target)
            if not existed:
                result.created.append(target)

        # Phase 5 -- remove. Last, deliberately.
        for target in doomed:
            try:
                target.unlink(missing_ok=True)
            except OSError:
                _roll_back(result, target)
                raise
            result.deleted.append(target)
    except OSError as e:
        logger.error("Multi-file write failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Could not write the prompt: {e}"
        ) from e
    finally:
        for leftover in staged.values():
            leftover.unlink(missing_ok=True)

    logger.info(
        "Wrote %d file(s), removed %d: %s",
        len(result.written),
        len(result.deleted),
        ", ".join(str(p) for p in result.written + result.deleted),
    )
    return result


def _roll_back(result: MultiWriteResult, failed: Path) -> None:
    """Restore everything already done before *failed* blew up."""
    # Deletes first: they happened last, so they are undone first.
    for removed in reversed(result.deleted):
        backup = result.backups.get(removed)
        if backup is None or not backup.exists():
            continue
        try:
            removed.write_bytes(backup.read_bytes())
            result.rolled_back.append(removed)
        except OSError as e:  # pragma: no cover - best effort, already failing
            logger.error("Could not restore %s after a failed delete: %s", removed, e)

    for done in reversed(result.written):
        backup = result.backups.get(done)
        if backup is None or not backup.exists():
            # It did not exist before, so "restoring" means removing it.
            done.unlink(missing_ok=True)
            result.rolled_back.append(done)
            continue
        try:
            done.write_bytes(backup.read_bytes())
            result.rolled_back.append(done)
        except OSError as e:  # pragma: no cover - best effort, already failing
            logger.error("Could not roll %s back after a failed write: %s", done, e)
    logger.error("Write of %s failed; rolled back %d file(s)", failed, len(result.rolled_back))
