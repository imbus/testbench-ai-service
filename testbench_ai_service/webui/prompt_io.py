"""Serializing a prompt document back to YAML.

Design D2: ``yaml.safe_dump``, not ``ruamel.yaml``. No new declared dependency,
and the cost is accepted -- the first console save strips any comment an
operator wrote by hand. Mitigated only where it is cheap and certain:

- ``sort_keys=False`` so key order survives,
- ``allow_unicode=True`` so the German prompts stay readable rather than
  escaping to ``\\uXXXX``,
- a wide ``width`` so block scalars are not reflowed into ribbons,
- ``None``-valued optional keys dropped rather than emitted as ``null``
  (pydantic treats an explicit ``null`` and an absent key differently for some
  fields, and the repo's own files simply omit them),
- and the ``# yaml-language-server: $schema=`` header re-emitted, since it is a
  fixed convention reconstructible from the file's depth under ``prompts_dir``.
"""

import os
from pathlib import Path
from typing import Any

import yaml

#: Wide enough that a long description stays on one line instead of being
#: folded, which would churn the diff of every neighbouring line.
_WIDTH = 4096

SCHEMA_FILENAME = "prompt.schema.json"


def prune_none(value: Any) -> Any:
    """Recursively drop mapping keys whose value is ``None``."""
    if isinstance(value, dict):
        return {k: prune_none(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [prune_none(v) for v in value]
    return value


def schema_header(prompt_path: Path, prompts_dir: Path) -> str | None:
    """The ``$schema`` comment for *prompt_path*, or ``None`` if no schema exists."""
    schema = Path(prompts_dir) / SCHEMA_FILENAME
    if not schema.is_file():
        return None
    relative = os.path.relpath(schema, Path(prompt_path).parent).replace(os.sep, "/")
    return f"# yaml-language-server: $schema={relative}"


def document_to_yaml(doc: dict[str, Any], header: str | None = None) -> str:
    """Render *doc* as the text to write to a ``prompt.yaml``."""
    body = yaml.safe_dump(
        prune_none(doc),
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
        width=_WIDTH,
    )
    return f"{header}\n\n{body}" if header else body
