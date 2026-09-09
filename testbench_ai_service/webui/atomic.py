"""Atomic file replacement for the console's writes.

A half-written ``config.toml`` is a service that will not start again. Every
console write therefore goes to a temp file in the *target's own directory*
-- ``os.replace`` is only atomic within a single filesystem, so a system temp
dir would silently give up the guarantee -- and the previous contents are kept
alongside as ``.bak`` before the replace.
"""

import os
import tempfile
from pathlib import Path

from fastapi import HTTPException, status

from testbench_ai_service.log import logger


def write_atomic(path: Path, text: str) -> Path | None:
    """Replace *path*'s contents with *text* atomically.

    The previous contents, if any, are copied to ``<path>.bak`` first. The
    backup is overwritten on each write rather than rotated: it exists so an
    operator can undo the last console save, not as a history.

    Returns:
        The backup path, or ``None`` when *path* did not exist.

    Raises:
        HTTPException 400: the directory does not exist, or the write, backup
            or replace failed (a permissions problem, a full disk, a file held
            open by another process on Windows).
    """
    target = Path(path)
    directory = target.parent
    if not directory.is_dir():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot write {target}: {directory} is not a directory",
        )

    backup: Path | None = None
    handle: int | None = None
    temp_path: Path | None = None
    try:
        handle, temp_name = tempfile.mkstemp(
            dir=str(directory), prefix=f".{target.name}.", suffix=".tmp"
        )
        temp_path = Path(temp_name)
        # newline="" keeps the text exactly as rendered: on Windows the default
        # would translate every "\n" to "\r\n", which changes every line of the
        # next diff and rewrites the whole file on a one-key edit.
        with os.fdopen(handle, "w", encoding="utf-8", newline="") as file:
            handle = None  # fdopen owns the descriptor now
            file.write(text)
            file.flush()
            os.fsync(file.fileno())

        # Capture backup info before replace, but only write it after replace succeeds
        backup_target = None
        if target.exists():
            backup_target = target.with_name(f"{target.name}.bak")
            backup_bytes = target.read_bytes()

        os.replace(temp_path, target)  # noqa: PTH105
        temp_path = None

        # Write backup after replace succeeds, so failed replace doesn't leave backup behind
        if backup_target is not None:
            backup = backup_target
            backup.write_bytes(backup_bytes)
    except OSError as e:
        logger.error("Atomic write to %s failed: %s", target, e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot write {target}: {e}",
        ) from e
    finally:
        if handle is not None:
            os.close(handle)
        if temp_path is not None and temp_path.exists():
            temp_path.unlink(missing_ok=True)

    logger.info("Wrote %s (backup: %s)", target, backup)
    return backup
