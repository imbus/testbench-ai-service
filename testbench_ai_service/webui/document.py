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
from typing import Any

import tomlkit
from fastapi import HTTPException, status
from tomlkit.container import OutOfOrderTableProxy
from tomlkit.exceptions import TOMLKitError
from tomlkit.items import InlineTable, Table

from testbench_ai_service.log import logger
from testbench_ai_service.utils.config import CONFIG_PREFIX
from testbench_ai_service.webui.edits import ConfigEdits


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


def service_table(document: tomlkit.TOMLDocument) -> Table | OutOfOrderTableProxy:
    """Return the live ``[testbench-ai-service]`` table, preserving existing keys and comments.

    If the existing value is a table (or an OutOfOrderTableProxy), return it
    live -- mutating it in place preserves the operator's comments and section
    order. An OutOfOrderTableProxy is what tomlkit returns when the section's
    sub-tables are split across the file by another top-level table; returning
    it live is the only way to keep comments and order intact. If it is an
    inline table (or a plain dict), promote it to a real table by copying every
    existing key/value into a fresh ``tomlkit.table()`` and reassigning it --
    inline tables cannot hold the nested sub-tables the console writes, so
    promotion is deliberate but preserves the operator's keys. If the key holds
    a non-table value (scalar, list), raise HTTPException 400 rather than
    silently destroying data.

    The returned table is the one inside *document*, not a copy -- callers
    mutate it in place and then render the document.

    Raises:
        HTTPException 400: if the existing value at the key is not a table
            (e.g., a scalar or list).
    """
    existing = document.get(CONFIG_PREFIX)
    if isinstance(existing, (Table, OutOfOrderTableProxy)):
        # Return live: preserves comments and section order.
        return existing
    if isinstance(existing, (InlineTable, dict)):
        # Promote inline table or dict to a real table, preserving keys.
        table = tomlkit.table()
        for key, value in existing.items():
            table[key] = value
        document[CONFIG_PREFIX] = table
        return table
    if existing is not None:
        # Existing but not a table (scalar, list, etc.) -- don't silently replace it.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"[{CONFIG_PREFIX}] must be a table, not {type(existing).__name__}",
        )
    # Key is absent; create empty table.
    table = tomlkit.table()
    document[CONFIG_PREFIX] = table
    return table


def apply_edits(document: tomlkit.TOMLDocument, edits: ConfigEdits) -> None:
    """Drive *edits* into *document* in place, under ``[testbench-ai-service]``.

    A ``None`` value removes the key so the model default takes over again;
    removing an absent key is a no-op. Intermediate tables are created as
    needed. Editing an existing value replaces the value alone, which is what
    keeps its comment attached.

    The paths in *edits* must already have been through
    :func:`~testbench_ai_service.webui.edits.validate_edit_paths`.

    Raises:
        HTTPException 400: a path's intermediate segment names an existing
            non-table value (a scalar or list left over from an older
            config) -- the same conflict
            :func:`~testbench_ai_service.webui.edits.merge_edits` raises for
            the equivalent dict, so the document path and the dict path
            agree on what they refuse.
    """
    root: Table | OutOfOrderTableProxy = service_table(document)
    for path, value in edits.items():
        segments = path.split(".")
        if value is None:
            _remove_key(root, segments)
        else:
            _set_key(root, path, segments, value)


def _child_table(node: Any, key: str, path: str) -> Any:
    """Return *node*'s child table at *key*, creating a real table if absent.

    An existing ``Table``, ``InlineTable`` or plain ``dict`` is edited in
    place. ``OutOfOrderTableProxy`` is named explicitly alongside them even
    though it is itself a dict subclass and would already fall into that arm
    by accident: mutating it in place -- rather than replacing it -- is
    exactly what preserves the operator's comments and section order, as in
    :func:`service_table`, so the case is spelled out rather than left to
    coincidence.

    An existing scalar or list is refused with HTTPException 400 rather than
    silently replaced by a fresh table -- exactly as :func:`service_table`
    refuses a non-table ``[testbench-ai-service]``, and as
    :func:`~testbench_ai_service.webui.edits._set_at` refuses a non-dict
    parent. A missing child (the normal case) is created as a fresh table.
    """
    child = node.get(key)
    if isinstance(child, (Table, OutOfOrderTableProxy, InlineTable, dict)):
        return child
    if child is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Edit path {path!r} conflicts with {key!r}, which is not a table",
        )
    child = tomlkit.table()
    node[key] = child
    return child


def _set_key(
    root: Table | OutOfOrderTableProxy, path: str, segments: list[str], value: Any
) -> None:
    node: Any = root
    for segment in segments[:-1]:
        node = _child_table(node, segment, path)
    node[segments[-1]] = _toml_value(value)


def _remove_key(root: Table | OutOfOrderTableProxy, segments: list[str]) -> None:
    node: Any = root
    for segment in segments[:-1]:
        child = node.get(segment) if hasattr(node, "get") else None
        if child is None:
            return
        node = child
    if hasattr(node, "get") and segments[-1] in node:
        del node[segments[-1]]


def _toml_value(value: Any) -> Any:
    """Convert a JSON-decoded value into a tomlkit item.

    ``tomlkit.item()`` handles scalars, lists and dicts. ``Path`` reaches here
    from nothing the browser sends, but a caller reusing this module with a
    pydantic dump would otherwise get an unserializable object, so it is
    stringified rather than left to fail at render time.
    """
    if isinstance(value, Path):
        return tomlkit.item(str(value))
    return tomlkit.item(value)
