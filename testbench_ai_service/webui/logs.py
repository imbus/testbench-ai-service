"""Tail and parse the service log for the console's Status screen."""

import re
from collections import deque
from pathlib import Path

from testbench_ai_service.log import logger
from testbench_ai_service.webui.models import LogLine

MAX_LIMIT = 500

# Matches the default file log_format:
#   %(asctime)s - %(levelname)8s - %(name)s - %(message)s
_LINE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})(?:,\d+)?"
    r"\s*-\s*(?P<level>[A-Z]+)"
    r"\s*-\s*(?P<source>\S+)"
    r"\s*-\s*(?P<message>.*)$"
)


def tail_lines(path: Path, limit: int) -> list[str]:
    """Return at most *limit* trailing lines of *path*, oldest first.

    A missing or unreadable log file yields an empty list: the Status screen
    should still render when logging to file is switched off.
    """
    try:
        with Path(path).open("r", encoding="utf-8", errors="replace") as handle:
            real_lines = (line.rstrip("\n") for line in handle if line.strip())
            return list(deque(real_lines, maxlen=limit))
    except OSError as e:
        logger.debug("Cannot read log file %s: %s", path, e)
        return []


def parse_log_line(text: str) -> LogLine:
    match = _LINE.match(text)
    if match is None:
        return LogLine(raw=text, message=text)
    return LogLine(
        raw=text,
        timestamp=match.group("ts"),
        level=match.group("level"),
        source=match.group("source"),
        message=match.group("message"),
    )


def read_log(path: Path, limit: int) -> list[LogLine]:
    """Newest first, which is the order the Status screen displays."""
    return [parse_log_line(line) for line in reversed(tail_lines(path, limit))]
