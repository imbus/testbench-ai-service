"""Multi-file replacement for the prompt editor's saves.

``atomic.write_atomic`` is single-file by construction, but saving one prompt
touches ``prompt.yaml`` plus every template file whose body changed.

This is **not** a journal and does not claim set-atomicity: ``os.replace`` is
atomic per file, and N files cannot be replaced as one operation. What it does
is stage every temp file *before* replacing any target, so directory existence,
write permission and disk space are proven for all N while all N are still
uncommitted -- which is where nearly everything that can go wrong does. The
residual window is the replace loop itself, and a failure inside it restores
the targets already replaced from their ``.bak``.
"""

import os
import tempfile
from pathlib import Path

from fastapi import HTTPException, status
from pydantic import BaseModel

from testbench_ai_service.log import logger


class MultiWriteResult(BaseModel):
    """What a completed :func:`write_all` did."""

    written: list[Path] = []
    #: target -> the ``.bak`` holding its previous contents. Absent for a file
    #: that did not exist before.
    backups: dict[Path, Path] = {}
    #: Targets restored after a mid-sequence failure. Only ever non-empty on
    #: the error path, which raises -- surfaced for the log, not for a caller.
    rolled_back: list[Path] = []


def _stage(target: Path, text: str) -> Path:
    """Write *text* to a temp file beside *target* and fsync it."""
    directory = target.parent
    if not directory.is_dir():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot write {target}: {directory} is not a directory",
        )
    handle, temp_name = tempfile.mkstemp(
        dir=str(directory), prefix=f".{target.name}.", suffix=".tmp"
    )
    # newline="" keeps the text exactly as rendered; the default would turn
    # every "\n" into "\r\n" on Windows and rewrite every line of the file.
    with os.fdopen(handle, "w", encoding="utf-8", newline="") as file:
        file.write(text)
        file.flush()
        os.fsync(file.fileno())
    return Path(temp_name)


def write_all(files: dict[Path, str]) -> MultiWriteResult:
    """Replace every target in *files* with its text.

    Raises:
        HTTPException 400: staging failed (nothing was replaced), or a replace
            failed part-way (the targets already replaced were restored).
    """
    if not files:
        return MultiWriteResult()

    targets = sorted(files, key=str)
    staged: dict[Path, Path] = {}
    result = MultiWriteResult()

    try:
        # Phase 1 -- stage everything. No target has changed yet.
        for target in targets:
            staged[target] = _stage(target, files[target])

        # Phase 2 -- back up what exists.
        for target in targets:
            if target.exists():
                backup = target.with_name(f"{target.name}.bak")
                backup.write_bytes(target.read_bytes())
                result.backups[target] = backup

        # Phase 3 -- replace. The only state-mutating calls on the targets.
        for target in targets:
            try:
                os.replace(staged[target], target)  # noqa: PTH105
            except OSError:
                _roll_back(result, target)
                raise
            staged.pop(target)
            result.written.append(target)
    except OSError as e:
        logger.error("Multi-file write failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Could not write the prompt: {e}"
        ) from e
    finally:
        for leftover in staged.values():
            leftover.unlink(missing_ok=True)

    logger.info(
        "Wrote %d file(s): %s", len(result.written), ", ".join(str(p) for p in result.written)
    )
    return result


def _roll_back(result: MultiWriteResult, failed: Path) -> None:
    """Restore the targets already replaced before *failed* blew up."""
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
