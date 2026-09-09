"""Validating a candidate configuration before anything is written.

The console must be incapable of writing a ``config.toml`` the service could
not boot with, so validation *is* constructing the very model the service boots
with -- ``AppConfig``. That gets the whole existing rule set for free: the URL
shape, the SSL files existing, agent class paths importing, prompt files
resolving, the Entra-ID-implies-Azure invariant.

Failures come back addressed to a field so the UI can mark the offending
input, in both the dotted spelling the console's forms use and the
``[section]`` spelling ``config.toml`` uses.
"""

import os
import re
from pathlib import Path
from typing import Any

import tomlkit
from pydantic import ValidationError

from testbench_ai_service.config import AppConfig
from testbench_ai_service.log import logger
from testbench_ai_service.utils.config import CONFIG_PREFIX
from testbench_ai_service.webui.models import ConfigIssue

_BARE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")
_LOG_FILE_SECTION = f"[{CONFIG_PREFIX}.logging.file]"


def _quote_key(segment: str) -> str:
    """Render one path segment as a TOML key, quoting when it is not a bare key.

    TestBench project names become table keys, and they contain spaces,
    punctuation, and potentially control characters. TOML basic strings forbid
    raw control characters, so escaping is delegated to tomlkit, which owns
    TOML serialization and handles all edge cases correctly.
    """
    if _BARE_KEY.match(segment):
        return segment
    try:
        return tomlkit.key(segment).as_string()
    except Exception:
        # If tomlkit fails on an exotic segment, the hint must not break the
        # response. Fall back to just the segment unchanged; the hint becomes
        # less helpful, but the validation result is still correct.
        return segment


def _toml_section(location: tuple[Any, ...]) -> str:
    """Spell a pydantic error location as the TOML section it lives in.

    Strip trailing array indices first (an error at trusted_proxies[2] belongs
    to [testbench-ai-service], not a nonexistent [testbench-ai-service.trusted_proxies]).
    Then drop the final remaining element (the key itself) to get the section.
    """
    parts = list(location)
    while parts and isinstance(parts[-1], int):
        parts.pop()
    if parts:
        parts.pop()
    segments = [_quote_key(str(p)) for p in parts if not isinstance(p, int)]
    return "[" + ".".join([CONFIG_PREFIX, *segments]) + "]"


def _issue_path(location: tuple[Any, ...]) -> str:
    return ".".join(str(part) for part in location)


def _log_file_writability_issue(config: AppConfig) -> ConfigIssue | None:
    """Check, with no side effect, whether the configured log file can be written.

    ``setup_logging`` builds a ``RotatingFileHandler`` from
    ``config.logging.file.file_name`` at both startup (``cli.py``) and hot
    reload, and raises ``ValueError`` there if the path is unusable -- by
    which point ``POST /admin/api/config/apply`` has already written the file
    to disk. Checking it here, before anything is written, is what keeps spec
    6.3's promise that the console cannot produce a ``config.toml`` the
    service could not boot with.

    Nothing is created or opened: an existing file must be writable in place;
    otherwise the parent directory must already exist and be writable, since
    ``RotatingFileHandler`` creates the file itself but never a missing
    directory. An empty or whitespace-only path is rejected explicitly first
    -- ``Path("").parent`` resolves to ``"."``, the current (writable)
    directory, and would otherwise pass.
    """
    file_name = config.logging.file.file_name
    if not file_name.strip():
        return ConfigIssue(
            path="logging.file.file_name",
            message="The log file path must not be empty.",
            toml_section=_LOG_FILE_SECTION,
        )

    path = Path(file_name)
    if path.exists():
        if os.access(path, os.W_OK):
            return None
        return ConfigIssue(
            path="logging.file.file_name",
            message=f"{path} exists but is not writable.",
            toml_section=_LOG_FILE_SECTION,
        )

    parent = path.parent
    if not parent.is_dir():
        return ConfigIssue(
            path="logging.file.file_name",
            message=f"The directory {parent} does not exist.",
            toml_section=_LOG_FILE_SECTION,
        )
    if not os.access(parent, os.W_OK):
        return ConfigIssue(
            path="logging.file.file_name",
            message=f"The directory {parent} is not writable.",
            toml_section=_LOG_FILE_SECTION,
        )
    return None


def validate_config_dict(data: dict[str, Any]) -> tuple[AppConfig | None, list[ConfigIssue]]:
    """Construct :class:`AppConfig` from *data*.

    Returns:
        ``(config, [])`` when *data* is a configuration the service could boot
        with, or ``(None, issues)`` when it is not. Never both.
    """
    try:
        config = AppConfig(**data)
    except ValidationError as e:
        issues = [
            ConfigIssue(
                path=_issue_path(error["loc"]),
                message=str(error.get("msg", "Invalid value")),
                toml_section=_toml_section(error["loc"]),
            )
            for error in e.errors()
        ]
        logger.info("Rejected a console config draft with %d issue(s)", len(issues))
        return None, issues
    except (Exception, SystemExit) as e:
        # AppConfig's model validators reach into the import system (agent
        # class paths) and the filesystem (prompt files). A failure there can
        # surface as something other than a ValidationError, and a 500 would
        # tell the operator nothing, so it becomes a root-addressed issue.
        # SystemExit is caught because this repo's own library code (in
        # utils/config.py) calls sys.exit(), and a validator importing such
        # code would otherwise propagate the exit. We do NOT catch bare
        # BaseException, which would also swallow KeyboardInterrupt,
        # GeneratorExit, and asyncio.CancelledError—turning Ctrl-C or a
        # cancelled request into an HTTP 400 would be worse than the
        # ImportError it catches.
        logger.exception("Unexpected failure validating a console config draft")
        return None, [ConfigIssue(path="", message=str(e), toml_section=f"[{CONFIG_PREFIX}]")]

    # AppConfig itself does not validate the log path -- see
    # _log_file_writability_issue's docstring for why that check belongs here,
    # in the console's validator, rather than tightening the model every CLI
    # user also goes through.
    log_issue = _log_file_writability_issue(config)
    if log_issue is not None:
        logger.info("Rejected a console config draft with 1 issue(s)")
        return None, [log_issue]

    return config, []
