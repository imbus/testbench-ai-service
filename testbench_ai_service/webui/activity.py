"""Read the activity sink for the console's Status screen (design D5/D6)."""

import json
import logging
from collections.abc import Iterator
from pathlib import Path

from pydantic import ValidationError

from testbench_ai_service.log import logger
from testbench_ai_service.models.logging import ActivityLoggerConfig
from testbench_ai_service.webui.models import ActivityEntry

MAX_LIMIT = 500

_LEVELS = {
    "CRITICAL": logging.CRITICAL,
    "ERROR": logging.ERROR,
    "WARNING": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
}


def _files_newest_first(cfg: ActivityLoggerConfig) -> list[Path]:
    base = Path(cfg.file_name)
    return [base] + [base.with_name(f"{base.name}.{i}") for i in range(1, cfg.backup_count + 1)]


def _lines_newest_first(path: Path) -> Iterator[str]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        logger.debug("Cannot read activity file %s: %s", path, e)
        return iter(())
    return reversed(text.splitlines())


def _visible(
    entry: dict, user_key: str | None, include_own: bool, include_service: bool, min_level: int
) -> bool:
    if _LEVELS.get(entry.get("level", ""), 0) < min_level:
        return False
    scope = entry.get("scope")
    if scope == "user":
        return include_own and user_key is not None and entry.get("user_key") == user_key
    if scope == "service":
        return include_service
    return False


def read_activity(
    cfg: ActivityLoggerConfig,
    *,
    user_key: str | None,
    include_own: bool,
    include_service: bool,
    min_level: int,
    limit: int,
) -> list[ActivityEntry]:
    """Newest first. The allow-list runs before the limit, so other users'
    entries can never push a user's own entries out of the window."""
    if not cfg.enabled:
        return []
    found: list[ActivityEntry] = []
    for path in _files_newest_first(cfg):
        for line in _lines_newest_first(path):
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if not isinstance(entry, dict):
                continue
            if not _visible(entry, user_key, include_own, include_service, min_level):
                continue
            try:
                found.append(
                    ActivityEntry(
                        timestamp=entry["ts"],
                        level=entry["level"],
                        source=entry["source"],
                        message=entry["message"],
                        scope=entry["scope"],
                        agent=entry.get("agent"),
                        project_key=entry.get("project_key"),
                        run_id=entry.get("run_id"),
                        exc=entry.get("exc"),
                    )
                )
            except (KeyError, ValidationError):
                continue
            if len(found) >= limit:
                return found
    return found
