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

import logging
import os
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import tomlkit
from pydantic import ValidationError

from testbench_ai_service.config import AppConfig
from testbench_ai_service.log import logger
from testbench_ai_service.utils.config import CONFIG_PREFIX, get_prompt_config
from testbench_ai_service.utils.prompt_utils import get_prompt_definition
from testbench_ai_service.webui.models import ConfigIssue
from testbench_ai_service.webui.paths import join_path, split_path

_BARE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")
_LOG_FILE_SECTION = f"[{CONFIG_PREFIX}.logging.file]"
_ACTIVITY_SECTION = f"[{CONFIG_PREFIX}.logging.activity]"
_CONSOLE_SECTION = f"[{CONFIG_PREFIX}.logging.console]"

# What Windows refuses in a file or directory name, whatever the directory.
_WINDOWS_FORBIDDEN = frozenset('<>:"|?*')
_WINDOWS_DEVICES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{n}" for n in range(1, 10)}
    | {f"LPT{n}" for n in range(1, 10)}
)


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


def _windows_name_problem(path: Path) -> str | None:
    """Why Windows cannot create *path*, judged by its names alone.

    The directory check passes for such a name -- its parent exists and is
    writable -- and only opening the file fails, which is after the write.
    """
    for part in path.parts[1:] if path.anchor else path.parts:
        if any(char in _WINDOWS_FORBIDDEN or ord(char) < 32 for char in part):  # noqa: PLR2004
            return f"'{part}' contains a character Windows does not allow in a file name."
        if part.split(".")[0].strip().upper() in _WINDOWS_DEVICES:
            return f"'{part}' is a device name on Windows and cannot be a file."
        if part not in {".", ".."} and part != part.rstrip(". "):
            return f"'{part}' must not end with a dot or a space on Windows."
    return None


def _log_format_problem(log_format: str) -> str | None:
    """Why *log_format* cannot format a log record, or ``None`` if it can.

    ``logging`` only checks the format when a handler is built from it, and an
    unknown field only when the first record is written -- both after the write.
    Formatting one record here finds either.
    """
    record = logging.LogRecord("name", logging.INFO, __file__, 1, "message", None, None)
    try:
        logging.Formatter(log_format).format(record)
    except KeyError as e:
        return f"Unknown log record field {e} in the log format."
    except (ValueError, TypeError) as e:
        return f"Not a usable log format: {e}"
    return None


def _log_format_issues(config: AppConfig) -> list[ConfigIssue]:
    """Check the console and file log formats the way ``setup_logging`` will use them."""
    candidates = [
        ("logging.console.log_format", config.logging.console.log_format, _CONSOLE_SECTION),
        ("logging.file.log_format", config.logging.file.log_format, _LOG_FILE_SECTION),
    ]
    issues = []
    for path, log_format, section in candidates:
        message = _log_format_problem(log_format)
        if message is not None:
            issues.append(ConfigIssue(path=path, message=message, toml_section=section))
    return issues


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
    if os.name == "nt":
        name_problem = _windows_name_problem(path)
        if name_problem is not None:
            return name_problem
    if path.exists():
        return _existing_path_problem(path)
    return _missing_leaf_problem(path.parent)


def _log_file_writability_issues(config: AppConfig) -> list[ConfigIssue]:
    """Check, with no side effect, whether the configured log files can be written.

    ``setup_logging`` builds a ``RotatingFileHandler`` from
    ``config.logging.file.file_name`` -- and, while the activity sink is
    enabled, from ``config.logging.activity.file_name`` -- at both startup
    (``cli.py``) and hot reload, and raises ``ValueError`` there if a path is
    unusable -- by which point ``POST /admin/api/config/apply`` has already
    written the file to disk. Checking them here, before anything is written,
    is what keeps spec 6.3's promise that the console cannot produce a
    ``config.toml`` the service could not boot with. See
    :func:`_log_file_problem` and its helpers for the actual checks.
    """
    candidates = [("logging.file.file_name", config.logging.file.file_name, _LOG_FILE_SECTION)]
    if config.logging.activity.enabled:
        candidates.append(
            ("logging.activity.file_name", config.logging.activity.file_name, _ACTIVITY_SECTION)
        )
    issues = []
    for path, file_name, section in candidates:
        message = _log_file_problem(file_name)
        if message is not None:
            issues.append(ConfigIssue(path=path, message=message, toml_section=section))
    return issues


def _scope_var_issues(
    config: AppConfig, agent_key: str, project: str | None, values: dict[str, Any]
) -> list[ConfigIssue]:
    """Check the prompt variables one scope sets for one agent against their declarations."""
    try:
        prompt_config = get_prompt_config(agent_key, config, project)
        definition = get_prompt_definition(prompt_config.file)
    except Exception:
        # An unreadable prompt is reported where it is configured, not once per variable.
        return []
    name = prompt_config.variant or definition.default_variant
    variant = next((v for v in definition.variants if v.name == name), None)
    if variant is None:
        return []
    scope: tuple[str, ...] = () if project is None else ("projects", project)
    issues = []
    for var_name, value in values.items():
        declared = variant.vars.get(var_name)
        problem = declared.problem_with(value) if declared is not None else None
        if problem is None:
            continue
        location = (*scope, "agents", agent_key, "prompt", "vars", var_name)
        issues.append(
            ConfigIssue(
                path=_issue_path(location),
                message=f"{declared.name}: {problem}",
                toml_section=_toml_section(location),
            )
        )
    return issues


def prompt_var_issues(config: AppConfig, edited: Iterable[str]) -> list[ConfigIssue]:
    """Prompt variable values among *edited* that their declaration does not accept.

    A variable is declared in the prompt file -- its type, an enum's choices, a
    number's bounds -- and ``AppConfig`` knows none of that, so a count of
    ``-5`` or ``"abc"`` is a valid configuration to it and only fails when the
    agent runs. Limited to the paths being edited: a value already in the file
    must not stand in the way of an unrelated change.
    """
    # Compared segment by segment: the same path may arrive with or without
    # quotes around a project name.
    edited_paths = [split_path(path) for path in edited]
    if not any("vars" in segments for segments in edited_paths):
        return []
    issues: list[ConfigIssue] = []
    for agent_key, agent in config.agents.items():
        issues += _scope_var_issues(config, agent_key, None, agent.prompt.vars or {})
    for project, project_config in config.projects.items():
        for agent_key, agent in (project_config.agents or {}).items():
            if agent_key in config.agents and agent.prompt is not None:
                issues += _scope_var_issues(config, agent_key, project, agent.prompt.vars or {})
    return [
        issue
        for issue in issues
        if any(split_path(issue.path)[: len(path)] == path for path in edited_paths)
    ]


def validate_config_dict(data: dict[str, Any]) -> tuple[AppConfig | None, list[ConfigIssue]]:
    """Construct :class:`AppConfig` from *data*.

    Returns:
        ``(config, [])`` when *data* is a configuration the service could boot
        with, or ``(None, issues)`` when it is not. Never both.
    """
    try:
        config = AppConfig(**data)
        log_issues = _log_file_writability_issues(config) + _log_format_issues(config)
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
        logger.exception("Unexpected failure validating a console config draft")
        return None, [ConfigIssue(path="", message=str(e), toml_section=f"[{CONFIG_PREFIX}]")]

    if log_issues:
        logger.info("Rejected a console config draft with %d issue(s)", len(log_issues))
        return None, log_issues

    return config, []
