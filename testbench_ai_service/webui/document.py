"""The console's ``config.toml`` document.

``config.toml`` is a hand-edited, commented file. Every console write goes
through a ``tomlkit`` document so that comments, key order and formatting
survive a save -- ``tomli_w``, which the ``init`` command uses, cannot preserve
any of them, and losing an operator's notes on first save would be a serious
regression.

This module knows about TOML and about the ``[testbench-ai-service]`` prefix.
It knows nothing about HTTP request shapes; see ``edits.py`` for those.
"""

from pathlib import Path

import tomlkit
from fastapi import HTTPException, status
from tomlkit.exceptions import TOMLKitError
from tomlkit.items import Table

from testbench_ai_service.log import logger
from testbench_ai_service.utils.config import CONFIG_PREFIX


def load_document(path: Path) -> tomlkit.TOMLDocument:
    """Parse *path* into an editable TOML document.

    An absent file yields a document holding nothing but an empty
    ``[testbench-ai-service]`` table: the service can run entirely on defaults,
    and the console must still be able to write the operator's first change.

    Raises:
        HTTPException 400: the file exists but is not valid TOML, is not
            readable, or is not decodable as UTF-8.
    """
    file_path = Path(path)
    if not file_path.is_file():
        logger.debug("No config file at %s; starting a fresh document", file_path)
        document = tomlkit.document()
        document[CONFIG_PREFIX] = tomlkit.table()
        return document
    try:
        text = file_path.read_text(encoding="utf-8")
        return tomlkit.parse(text)
    except (TOMLKitError, OSError, UnicodeDecodeError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{file_path} is not valid TOML: {e}",
        ) from e


def render_document(document: tomlkit.TOMLDocument) -> str:
    """Serialize *document* back to TOML text."""
    return tomlkit.dumps(document)


def service_table(document: tomlkit.TOMLDocument) -> Table:
    """Return the live ``[testbench-ai-service]`` table, creating it if absent.

    The returned table is the one inside *document*, not a copy -- callers
    mutate it in place and then render the document.
    """
    existing = document.get(CONFIG_PREFIX)
    if isinstance(existing, Table):
        return existing
    table = tomlkit.table()
    document[CONFIG_PREFIX] = table
    return table
