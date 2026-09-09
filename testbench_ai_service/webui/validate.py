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

import re
from typing import Any

from pydantic import ValidationError

from testbench_ai_service.config import AppConfig
from testbench_ai_service.log import logger
from testbench_ai_service.utils.config import CONFIG_PREFIX
from testbench_ai_service.webui.models import ConfigIssue

_BARE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")


def _quote_key(segment: str) -> str:
    """Render one path segment as a TOML key, quoting when it is not a bare key.

    TestBench project names become table keys, and they contain spaces and
    punctuation, so the naive dotted join produces invalid TOML an operator
    cannot paste into config.toml.
    """
    if _BARE_KEY.match(segment):
        return segment
    escaped = segment.replace("\\", "\\\\").replace('"', '\\"')
    return '"' + escaped + '"'


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


def validate_config_dict(data: dict[str, Any]) -> tuple[AppConfig | None, list[ConfigIssue]]:
    """Construct :class:`AppConfig` from *data*.

    Returns:
        ``(config, [])`` when *data* is a configuration the service could boot
        with, or ``(None, issues)`` when it is not. Never both.
    """
    try:
        return AppConfig(**data), []
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
