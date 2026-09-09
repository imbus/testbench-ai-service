"""Reading the service's TOML configuration for the console.

Phase 1 only reads.  The write path in phase 2 builds on ``read_config_file`` and
adds a comment-preserving ``tomlkit`` round trip.
"""

import sys
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status

from testbench_ai_service.config import AppConfig
from testbench_ai_service.log import logger
from testbench_ai_service.utils.config import CONFIG_PREFIX
from testbench_ai_service.webui.models import ConfigResponse

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


# Case-insensitive substring matches against key NAMES only -- never against
# values. "api_key"/"apikey" are compound tokens deliberately: a bare "key"
# pattern would wrongly catch `ssl_key`, which is a certificate file path, not
# a secret, and the compound form leaves `api_version` alone.
_REDACT_KEY_SUBSTRINGS = ("secret", "password", "token", "credential", "api_key", "apikey")
REDACTED_SENTINEL = "***REDACTED***"


def _looks_like_credential_key(key: str) -> bool:
    lowered = key.lower()
    return any(pattern in lowered for pattern in _REDACT_KEY_SUBSTRINGS)


def redact_credentials(data: dict[str, Any]) -> dict[str, Any]:
    """Recursively replace the values of credential-named keys with a sentinel.

    Matches on key names only, case-insensitively, never on values -- so
    ``{"auth_method": "api_key"}`` (a legitimate enum value) is left alone
    while ``{"api_key": "sk-..."}`` (an operator's mistake, or a real secret)
    is not. The sentinel replaces the value rather than dropping the key, so
    the console can still show that a value is set.

    Applies uniformly to every key at every level: ``disk`` is a plain dict
    read straight off the filesystem with no declared-vs-extra distinction to
    exploit, so there is nothing narrower to key off than the name itself.
    """
    redacted: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, dict):
            redacted[key] = redact_credentials(value)
        elif _looks_like_credential_key(key):
            redacted[key] = REDACTED_SENTINEL
        else:
            redacted[key] = value
    return redacted


def read_config_file(path: Path) -> dict[str, Any]:
    """Return the ``[testbench-ai-service]`` table from *path*.

    An absent file yields ``{}`` -- the service can run entirely on defaults,
    and the console must still be able to render the config screens.

    Raises:
        HTTPException 400: the file exists but is not valid TOML, cannot be
            read (e.g. a permissions problem), or is not decodable as UTF-8.
    """
    file_path = Path(path)
    if not file_path.is_file():
        logger.debug("No config file at %s", file_path)
        return {}
    try:
        with file_path.open("rb") as handle:
            document = tomllib.load(handle)
    except (tomllib.TOMLDecodeError, OSError, UnicodeDecodeError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{file_path} is not valid TOML: {e}",
        ) from e
    return dict(document.get(CONFIG_PREFIX, {}))


def running_config(config: AppConfig) -> dict[str, Any]:
    """The in-memory config as JSON-safe primitives."""
    return config.model_dump(mode="json")


def build_config_response(config: AppConfig, path: Path) -> ConfigResponse:
    """Assemble the console's config payload: running config, disk config, and
    the path the service loaded from.

    Both ``running`` and ``disk`` are passed through :func:`redact_credentials`
    before leaving this function -- ``disk`` is raw file content independent
    of any pydantic model, so a credential planted in the file must be caught
    here regardless of what the model would or would not have allowed.
    """
    disk = redact_credentials(read_config_file(path))
    running = redact_credentials(running_config(config))
    return ConfigResponse(
        running=running,
        disk=disk,
        config_path=str(Path(path).resolve()),
    )
