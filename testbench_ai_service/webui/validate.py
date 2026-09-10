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
from testbench_ai_service.webui.paths import join_path

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
    """Spell a pydantic error location the way the console addresses the field.

    Through the tokenizer, not a plain join: the forms match an issue to an
    input by comparing this string against the path they built, and a project
    name that needs quoting is quoted there. An array index is a bare segment
    and comes through unchanged.
    """
    parts = [str(part) for part in location]
    # A model-level error carries no location at all; it stays the empty
    # string the root-addressed issues already used.
    return join_path(parts) if parts else ""


def _existing_path_problem(path: Path) -> str | None:
    """Why *path*, which already exists, cannot be used as the log file.

    An existing path that is a directory rather than a file is rejected:
    ``os.access(a_directory, os.W_OK)`` is true for a writable directory --
    being writable is exactly what lets files be created inside it -- so
    ``exists()`` plus ``os.access()`` alone would call a directory a valid
    log file. ``RotatingFileHandler`` cannot open a directory as a file and
    raises ``ValueError`` there; ``path.is_file()`` is what actually
    discriminates an existing file from an existing directory.
    """
    if not path.is_file():
        return f"{path} exists but is not a file; a log file path is expected."
    if not os.access(path, os.W_OK):
        return f"{path} exists but is not writable."
    return None


def _missing_leaf_problem(parent: Path) -> str | None:
    """Why a not-yet-existing log file under *parent* cannot be created there.

    ``RotatingFileHandler`` creates the file itself but never a missing
    directory, so *parent* must already exist and be writable.
    """
    if not parent.is_dir():
        return f"The directory {parent} does not exist."
    if not os.access(parent, os.W_OK):
        return f"The directory {parent} is not writable."
    return None


def _log_file_problem(file_name: str) -> str | None:
    """Why *file_name* cannot be used as the log file, or ``None`` if it can.

    Pure and side-effect free: nothing is created or opened. An empty or
    whitespace-only path is rejected explicitly first -- ``Path("").parent``
    resolves to ``"."``, the current (writable) directory, and would
    otherwise pass.
    """
    if not file_name.strip():
        return "The log file path must not be empty."

    path = Path(file_name)
    if path.exists():
        return _existing_path_problem(path)
    return _missing_leaf_problem(path.parent)


def _log_file_writability_issue(config: AppConfig) -> ConfigIssue | None:
    """Check, with no side effect, whether the configured log file can be written.

    ``setup_logging`` builds a ``RotatingFileHandler`` from
    ``config.logging.file.file_name`` at both startup (``cli.py``) and hot
    reload, and raises ``ValueError`` there if the path is unusable -- by
    which point ``POST /admin/api/config/apply`` has already written the file
    to disk. Checking it here, before anything is written, is what keeps spec
    6.3's promise that the console cannot produce a ``config.toml`` the
    service could not boot with. See :func:`_log_file_problem` and its
    helpers for the actual checks.
    """
    message = _log_file_problem(config.logging.file.file_name)
    if message is None:
        return None
    return ConfigIssue(
        path="logging.file.file_name",
        message=message,
        toml_section=_LOG_FILE_SECTION,
    )


def validate_config_dict(data: dict[str, Any]) -> tuple[AppConfig | None, list[ConfigIssue]]:
    """Construct :class:`AppConfig` from *data*.

    Returns:
        ``(config, [])`` when *data* is a configuration the service could boot
        with, or ``(None, issues)`` when it is not. Never both.
    """
    try:
        config = AppConfig(**data)
        # AppConfig itself does not validate the log path -- see
        # _log_file_writability_issue's docstring for why that check belongs
        # here, in the console's validator, rather than tightening the model
        # every CLI user also goes through. It runs inside this same guard,
        # not after it: it touches the filesystem exactly like the model
        # validators above it (prompt files, SSL files), and an unexpected
        # OSError escaping it here would otherwise reproduce the raw-500
        # pattern the except clause below exists to prevent -- one that,
        # after a write has already committed, is exactly what FIX C
        # (apply_config's post-write re-read) was built to stop happening a
        # second way.
        log_issue = _log_file_writability_issue(config)
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

    if log_issue is not None:
        logger.info("Rejected a console config draft with 1 issue(s)")
        return None, [log_issue]

    return config, []
