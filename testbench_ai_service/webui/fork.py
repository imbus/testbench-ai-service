"""Copy a prompt for one project, and point that project at the copy.

A fork is a sibling agent directory, ``prompts_dir/<lang>/<agent>__<slug>/``,
beside the prompt it copies. That is the only layout ``build_tree`` (exactly two
levels) and the ``{lang}/{agent}`` route key already address, so a fork is
visible in the tree and editable on the first request after it is created --
with no new addressing code anywhere (design D3).

The ``config.toml`` value carries its language prefix, ``<lang>/<dir>/prompt.yaml``.
Both resolvers try ``prompts_dir/<file>`` as their second candidate, so the
prefixed value is correct under the runtime resolver AND under the boot
validator whichever language directory the fork lands in -- and a fork then
means exactly one file, which a later change to the project's language must not
silently repoint (design D2).

Templates are copied as **bytes** under their basename. Copying is the point: a
fork referencing the originals would edit the file it forked away from. Bytes
rather than decoded text means an undecodable or CRLF template copies faithfully
(design D6).

This module builds and rolls back. It does not write: the route owns the order
in which the prompt files and ``config.toml`` are committed (design 5.3).
"""

import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status
from pydantic import BaseModel

from testbench_ai_service.log import logger
from testbench_ai_service.webui.prompt_io import document_to_yaml, prune_none, schema_header
from testbench_ai_service.webui.prompts import _load_definition, resolve_template_file
from testbench_ai_service.webui.security import resolve_within

#: Everything outside this collapses to a single "-".
_SLUG_ALLOWED = re.compile(r"[^a-z0-9._-]+")
_SLUG_MAX = 40


class ForkPlan(BaseModel):
    """A fork, computed without touching anything."""

    target_dir: Path
    #: The directory's own name -- the ``{agent}`` the new prompt answers to.
    agent_dir: str
    files: dict[Path, str | bytes] = {}
    #: What ``projects.<name>.agents.<agent>.prompt.file`` becomes.
    config_value: str


def slugify_project(name: str) -> str:
    """A filesystem-safe segment derived from a TestBench project name."""
    slug = _SLUG_ALLOWED.sub("-", name.strip().lower()).strip("-")
    return slug[:_SLUG_MAX].strip("-")


def _require_segment(prompts_dir: Path, lang: str, directory: str) -> Path:
    """Resolve *directory* as a single segment under ``prompts_dir/<lang>``."""
    if not directory.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "The project name does not produce a usable directory name. Supply one explicitly."
            ),
        )
    candidate = Path(directory)
    if candidate.is_absolute() or len(candidate.parts) != 1 or directory in {".", ".."}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{directory!r} is not a plain directory name.",
        )
    language_dir = resolve_within(Path(prompts_dir), lang)
    return resolve_within(Path(prompts_dir), language_dir / candidate)


def build_fork(
    prompts_dir: Path,
    prompt_path: Path,
    lang: str,
    agent: str,
    directory: str | None,
    project: str,
) -> ForkPlan:
    """Everything the fork would create, and the config value pointing at it.

    Raises:
        HTTPException 400: the directory name is not a single usable segment, or
            escapes ``prompts_dir``.
        HTTPException 404: the source prompt does not parse, or a template it
            references cannot be read.
        HTTPException 409: the target directory already exists, or two templates
            collide on basename.
    """
    base = Path(prompts_dir)
    definition = _load_definition(Path(prompt_path), base)

    name = directory if directory is not None else f"{agent}__{slugify_project(project)}"
    target_dir = _require_segment(base, lang, name)
    if target_dir.exists():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"{target_dir.name!r} already exists under {lang}/. Choose a different "
                f"directory name."
            ),
        )

    files: dict[Path, str | bytes] = {}
    #: basename -> the source path it was copied from, for the collision check.
    copied: dict[str, Path] = {}
    document: dict[str, Any] = {
        "name": definition.name,
        "summary": definition.summary,
        "description": definition.description,
        "default_model": definition.default_model,
        "default_variant": definition.default_variant,
        "variants": [],
    }

    for variant in definition.variants:
        messages: list[dict[str, Any]] = []
        for message in variant.messages:
            if message.file is None:
                messages.append({"role": message.role, "text": message.text})
                continue
            source = resolve_template_file(base, Path(prompt_path), message.file)
            basename = source.name
            previous = copied.get(basename)
            if previous is not None and previous != source:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"{previous.name!r} and {source.name!r} would both be copied to "
                        f"{basename!r}. Rename one of them before forking."
                    ),
                )
            try:
                # Bytes, not text: an undecodable or CRLF template copies exactly.
                # Only a missing or unopenable file refuses the fork -- decodability
                # is a different question, and not this one.
                files[target_dir / basename] = source.read_bytes()
            except OSError as e:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"The template {message.file!r} could not be read: {e}",
                ) from e
            copied[basename] = source
            messages.append({"role": message.role, "file": basename})

        document["variants"].append(
            {
                "name": variant.name,
                "description": variant.description,
                "model": variant.model,
                "vars": {key: prune_none(decl.model_dump()) for key, decl in variant.vars.items()},
                "messages": messages,
            }
        )

    target_prompt = target_dir / "prompt.yaml"
    files[target_prompt] = document_to_yaml(document, header=schema_header(target_prompt, base))

    logger.info("Planned a fork of %s for project %r at %s", prompt_path, project, target_dir)
    return ForkPlan(
        target_dir=target_dir,
        agent_dir=target_dir.name,
        files=files,
        config_value=f"{lang}/{target_dir.name}/prompt.yaml",
    )


def rollback_fork(created: Sequence[Path], target_dir: Path) -> None:
    """Undo a fork whose config write failed.

    A true undo rather than a best-effort one: every path in *created* is new,
    so there is no previous content that could fail to be restored.
    """
    for path in created:
        try:
            path.unlink(missing_ok=True)
            backup = path.with_name(f"{path.name}.bak")
            backup.unlink(missing_ok=True)
        except OSError as e:  # pragma: no cover - best effort, already failing
            logger.error("Could not remove %s while rolling back a fork: %s", path, e)
    try:
        Path(target_dir).rmdir()
    except OSError:
        logger.warning("Left %s in place: it is not empty", target_dir)
