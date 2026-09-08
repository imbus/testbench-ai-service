"""Reading the service's TOML configuration for the console.

Phase 1 only reads.  The write path in phase 2 builds on ``read_config_file`` and
adds a comment-preserving ``tomlkit`` round trip.
"""

from pathlib import Path
from typing import Any

from fastapi import HTTPException, status

from testbench_ai_service.config import AppConfig
from testbench_ai_service.log import logger
from testbench_ai_service.utils.config import CONFIG_PREFIX
from testbench_ai_service.webui.models import ConfigResponse

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib  # type: ignore[no-redef]


def read_config_file(path: Path) -> dict[str, Any]:
    """Return the ``[testbench-ai-service]`` table from *path*.

    An absent file yields ``{}`` -- the service can run entirely on defaults,
    and the console must still be able to render the config screens.

    Raises:
        HTTPException 400: the file exists but is not valid TOML.
    """
    file_path = Path(path)
    if not file_path.is_file():
        logger.debug("No config file at %s", file_path)
        return {}
    try:
        with file_path.open("rb") as handle:
            document = tomllib.load(handle)
    except tomllib.TOMLDecodeError as e:
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
    the path the service loaded from."""
    disk = read_config_file(path)
    running = running_config(config)
    return ConfigResponse(
        running=running,
        disk=disk,
        config_path=str(Path(path).resolve()),
    )
