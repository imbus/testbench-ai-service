"""Read-only prompt metadata for the console (design D7).

The agent-detail form cannot be built from ``config.toml`` alone. Which variant
names are valid, and what type each ``vars`` entry is, are declared in the
prompt YAML -- not in the config. Without reading them, ``variant`` is free text
whose typos fall back to ``default_variant`` silently at runtime (a
wrong-output bug with no error anywhere) and ``vars`` is an untyped key/value
grid.

**Metadata only.** Message templates and template file contents are phase 4's
prompt editor. This module reads the header, the variant list, and the variable
declarations, and nothing else.

Every path this module opens is request-controlled, through three separate
segments (``{lang}``, the agent's declared ``prompt.file``, and ``?file=``), so
all of them go through :func:`~testbench_ai_service.webui.security.resolve_within`
and then through an extension allowlist applied to the **resolved** path -- as
``security``'s module docstring requires, because a string-level check is
defeated by ``p.yaml.`` (suffix ``"."``) and ``p.yaml:evil`` (an NTFS alternate
data stream, suffix ``".yaml:evil"``).
"""

from pathlib import Path
from typing import Any

import yaml
from fastapi import HTTPException, status
from pydantic import ValidationError

from testbench_ai_service.config import AppConfig
from testbench_ai_service.log import logger
from testbench_ai_service.models.prompt import PromptDefinition
from testbench_ai_service.utils.prompt_utils import get_prompt_definition
from testbench_ai_service.webui.models import PromptMetaResponse, PromptVariantMeta
from testbench_ai_service.webui.security import resolve_within

#: Prompt metadata is YAML. ``prompts_dir`` also holds the Jinja templates the
#: messages point at, and containment alone would let ``?file=`` read any of
#: them; this narrows the endpoint to the files it actually parses.
PROMPT_SUFFIXES = frozenset({".yaml", ".yml"})


def declared_prompt_file(
    agent_key: str, on_disk: dict[str, Any], running: AppConfig
) -> Path | None:
    """The prompt file ``config.toml`` declares for *agent_key*, or ``None``.

    Prefers the value in the **on-disk** table over the running config, because
    that is the value the console's forms display: ``GET /config`` shows
    ``disk``, so resolving metadata from the running config instead would render
    a hand-edited file the process has not taken up yet against the wrong
    prompt.

    Falls back to *running* per field rather than wholesale, which is what the
    ``agents`` merge semantics already do: a config that declares no ``[agents]``
    block at all, or one that overrides only ``prompt.variant``, still inherits
    the built-in's ``prompt.file``.
    """
    agents = on_disk.get("agents")
    if isinstance(agents, dict):
        block = agents.get(agent_key)
        if isinstance(block, dict):
            prompt = block.get("prompt")
            if isinstance(prompt, dict):
                declared = prompt.get("file")
                if isinstance(declared, str) and declared.strip():
                    return Path(declared)

    agent = running.agents.get(agent_key)
    return None if agent is None else Path(agent.prompt.file)


def _require_prompt_suffix(path: Path) -> None:
    if path.suffix.lower() not in PROMPT_SUFFIXES:
        logger.warning("Refused a non-YAML prompt metadata read: %r", str(path))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Prompt metadata can only be read from a .yaml or .yml file",
        )


def resolve_prompt_file(prompts_dir: Path, lang: str, file: str | Path) -> Path:
    """Locate *file* for language *lang* under *prompts_dir*.

    Mirrors :func:`~testbench_ai_service.validators.resolve_prompt_file_path`:
    ``prompts_dir/<lang>/<file>`` first, then ``prompts_dir/<file>``. Diverging
    from it would mean the console 404s on a prompt the service boots with
    happily.

    Containment is checked against *prompts_dir* rather than against the
    language directory, so a prompt shared between languages resolves the same
    way it does at runtime -- but a ``{lang}`` segment that tries to climb out
    is still refused, because the language directory is resolved through
    ``resolve_within`` first.

    Raises:
        HTTPException 400: *file* is empty, escapes *prompts_dir*, or is not a
            ``.yaml``/``.yml`` file.
        HTTPException 404: neither candidate is a readable file.
    """
    candidate = str(file)
    if not candidate.strip():
        # Path("") is Path(".") and resolves to the base directory itself, so
        # without this guard an empty ?file= would silently become "read the
        # language directory". resolve_within's own empty check cannot see this
        # case once the caller has joined the value onto a base path.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Empty path is not allowed"
        )

    base = Path(prompts_dir)
    file_path = Path(candidate)
    if file_path.is_absolute():
        candidates = [resolve_within(base, file_path)]
    else:
        language_dir = resolve_within(base, lang)
        candidates = [
            resolve_within(base, language_dir / file_path),
            resolve_within(base, file_path),
        ]

    # Every candidate is suffix-checked before any of them is stat'ed, so a
    # refused extension is refused whether or not the file happens to exist.
    for path in candidates:
        _require_prompt_suffix(path)
    for path in candidates:
        if path.is_file():
            return path

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"No prompt file for {candidate!r} under {base}",
    )


def _variant_meta(definition: PromptDefinition) -> list[PromptVariantMeta]:
    return [
        PromptVariantMeta(
            name=variant.name,
            description=variant.description,
            model=variant.model,
            vars=variant.vars,
        )
        for variant in definition.variants
    ]


def read_prompt_meta(path: Path) -> PromptMetaResponse:
    """Parse *path* into console metadata.

    Raises:
        HTTPException 404: the file is gone, or is not a file at all. Risk 3:
            a ``prompts_dir`` that moved since boot must give a clean 404 rather
            than a 500 the operator cannot interpret.
        HTTPException 422: the file is there but is not a usable prompt
            definition. The reason is passed through -- the operator is the only
            person who can fix the file, so hiding it behind a bare 500 would
            leave them guessing.
    """
    try:
        definition = get_prompt_definition(path)
    except (FileNotFoundError, IsADirectoryError, PermissionError, NotADirectoryError) as e:
        logger.warning("Prompt metadata unavailable at %s: %s", path, e)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"No prompt file at {path}"
        ) from e
    except OSError as e:
        # A directory where the file should be surfaces as PermissionError on
        # Windows and IsADirectoryError on POSIX; anything else the filesystem
        # raises is still "we could not read it", not a bug in the console.
        logger.warning("Could not read the prompt file at %s: %s", path, e)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"No prompt file at {path}"
        ) from e
    except (yaml.YAMLError, ValidationError, ValueError) as e:
        logger.warning("Prompt file %s is not a usable prompt definition: %s", path, e)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"The prompt file at {path} could not be read: {e}",
        ) from e

    return PromptMetaResponse(
        name=definition.name,
        summary=definition.summary,
        description=definition.description,
        default_model=definition.default_model,
        default_variant=definition.default_variant,
        variants=_variant_meta(definition),
    )
