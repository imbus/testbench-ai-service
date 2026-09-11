"""Read-only prompt metadata for the console (design D7).

The agent-detail form cannot be built from ``config.toml`` alone. Which variant
names are valid, and what type each ``vars`` entry is, are declared in the
prompt YAML -- not in the config. Without reading them, ``variant`` is free text
whose typos fall back to ``default_variant`` silently at runtime (a
wrong-output bug with no error anywhere) and ``vars`` is an untyped key/value
grid.

**Metadata, and the full editable document.** ``read_prompt_meta`` reads the
header, the variant list, and the variable declarations, and nothing else.
``read_prompt_document`` builds on the same parsed definition to also resolve
every message's body -- inline or from a referenced template file -- for
phase 4's prompt editor.

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
from testbench_ai_service.models.prompt import MessageTemplate, PromptDefinition
from testbench_ai_service.utils.prompt_utils import get_prompt_definition
from testbench_ai_service.webui.models import (
    PromptDocumentResponse,
    PromptMessageDoc,
    PromptMetaResponse,
    PromptSaveRequest,
    PromptTreeEntry,
    PromptTreeLanguage,
    PromptTreeResponse,
    PromptVariantDoc,
    PromptVariantMeta,
)
from testbench_ai_service.webui.prompt_io import document_to_yaml, prune_none, schema_header
from testbench_ai_service.webui.prompt_render import context_skeleton
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

    logger.warning("No prompt file for %r under %s", candidate, base)
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"No prompt file for {candidate!r}",
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


def _display_name(path: Path, prompts_dir: Path | None) -> str:
    """How a prompt file is named back to the browser.

    Relative to ``prompts_dir`` when it lives there, which is the spelling the
    operator wrote in ``config.toml``. The absolute path is a detail of the
    server's filesystem, and this endpoint is open to every signed-in user,
    not only an administrator.
    """
    if prompts_dir is not None:
        try:
            return path.relative_to(prompts_dir).as_posix()
        except ValueError:
            pass
    return path.name


def _load_definition(path: Path, prompts_dir: Path | None) -> PromptDefinition:
    """Parse *path* into a :class:`PromptDefinition`.

    Shared by :func:`read_prompt_meta` and :func:`read_prompt_document` --
    both need the same file parsed the same way, and the same 404/422
    behaviour is what the caller reports back to the operator.

    Raises:
        HTTPException 404: the file is gone, or is not a file at all. Risk 3:
            a ``prompts_dir`` that moved since boot must give a clean 404 rather
            than a 500 the operator cannot interpret.
        HTTPException 422: the file is there but is not a usable prompt
            definition. The response names the file and what is wrong with it
            structurally -- which fields, or where the YAML broke -- but never
            the offending values: a pydantic error embeds its input, and
            ``?file=`` can be aimed at any YAML under ``prompts_dir``. The full
            error goes to the log, where the operator can already read the file
            itself.
    """
    display = _display_name(path, prompts_dir)
    try:
        return get_prompt_definition(path)
    except (FileNotFoundError, IsADirectoryError, PermissionError, NotADirectoryError) as e:
        logger.warning("Prompt metadata unavailable at %s: %s", path, e)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"No prompt file at {display}"
        ) from e
    except OSError as e:
        # A directory where the file should be surfaces as PermissionError on
        # Windows and IsADirectoryError on POSIX; anything else the filesystem
        # raises is still "we could not read it", not a bug in the console.
        logger.warning("Could not read the prompt file at %s: %s", path, e)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"No prompt file at {display}"
        ) from e
    except yaml.YAMLError as e:
        logger.warning("Prompt file %s is not valid YAML: %s", path, e)
        mark = getattr(e, "problem_mark", None)
        where = f" at line {mark.line + 1}, column {mark.column + 1}" if mark else ""
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"The prompt file {display} is not valid YAML{where}",
        ) from e
    except ValidationError as e:
        logger.warning("Prompt file %s is not a usable prompt definition: %s", path, e)
        fields = ", ".join(
            sorted(
                {".".join(str(part) for part in error["loc"]) or "(root)" for error in e.errors()}
            )
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"The prompt file {display} is not a usable prompt definition: {fields}",
        ) from e
    except ValueError as e:
        logger.warning("Prompt file %s is not a usable prompt definition: %s", path, e)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"The prompt file {display} is not a usable prompt definition",
        ) from e


def read_prompt_meta(path: Path, prompts_dir: Path | None = None) -> PromptMetaResponse:
    """Parse *path* into console metadata.

    Raises:
        HTTPException 404: the file is gone, or is not a file at all.
        HTTPException 422: the file is there but is not a usable prompt
            definition. See :func:`_load_definition` for the detail.
    """
    definition = _load_definition(path, prompts_dir)

    return PromptMetaResponse(
        name=definition.name,
        summary=definition.summary,
        description=definition.description,
        default_model=definition.default_model,
        default_variant=definition.default_variant,
        variants=_variant_meta(definition),
    )


#: Message templates are Jinja. These are exactly the suffixes
#: ``MessageTemplate``'s docstring names.
TEMPLATE_SUFFIXES = frozenset({".jinja", ".j2", ".md"})


def _require_template_suffix(path: Path) -> None:
    if path.suffix.lower() not in TEMPLATE_SUFFIXES:
        logger.warning("Refused a non-template file read: %r", str(path))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A message template must be a .jinja, .j2 or .md file",
        )


def resolve_template_file(prompts_dir: Path, prompt_path: Path, ref: str) -> Path:
    """Locate a message template *ref* declared by the prompt at *prompt_path*.

    Resolved against the prompt YAML's **own directory**, because that is what
    ``MessageTemplate.get_content(base_path)`` does at runtime with
    ``base_path = Path(prompt_config.file).parent``. Resolving anywhere else
    would mean the console edits a different file from the one the agent reads.

    Containment is then checked against *prompts_dir*, not against the prompt's
    directory, so a template shared between agents resolves the way it does at
    runtime while a reference climbing out of ``prompts_dir`` is still refused.

    Raises:
        HTTPException 400: *ref* is empty, escapes *prompts_dir*, or is not an
            allowlisted template suffix.
        HTTPException 404: nothing readable is there.
    """
    if not ref.strip():
        # Path("") is Path("."), which resolves to a directory rather than
        # raising -- see security.py's module docstring.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Empty path is not allowed"
        )

    base = Path(prompts_dir)
    candidate = Path(ref)
    target = (
        resolve_within(base, candidate)
        if candidate.is_absolute()
        else resolve_within(base, Path(prompt_path).parent / candidate)
    )

    # Suffix-checked before it is stat'ed, so a refused extension is refused
    # whether or not the file happens to exist.
    _require_template_suffix(target)
    if not target.is_file():
        logger.warning("No template file for %r under %s", ref, base)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"No template file for {ref!r}"
        )
    return target


def read_prompt_document(
    prompt_path: Path, prompts_dir: Path, lang: str, agent: str
) -> PromptDocumentResponse:
    """The full editable document: the YAML plus every referenced template body.

    A template that is missing, unreadable, or points outside ``prompts_dir``
    yields ``readable=False`` and an empty body rather than failing the whole
    document. The operator has to *see* a broken reference to repair it.
    """
    definition = _load_definition(prompt_path, prompts_dir)
    base = Path(prompts_dir)

    variants: list[PromptVariantDoc] = []
    for variant in definition.variants:
        messages = [_message_doc(m, prompt_path, base) for m in variant.messages]
        variants.append(
            PromptVariantDoc(
                name=variant.name,
                description=variant.description,
                model=variant.model,
                vars=variant.vars,
                messages=messages,
            )
        )

    bodies = [message.content for variant in variants for message in variant.messages]
    return PromptDocumentResponse(
        lang=lang,
        agent=agent,
        file=_display_name(prompt_path, base),
        name=definition.name,
        summary=definition.summary,
        description=definition.description,
        default_model=definition.default_model,
        default_variant=definition.default_variant,
        variants=variants,
        agent_context_skeleton=context_skeleton(bodies),
    )


def _message_doc(
    message: MessageTemplate, prompt_path: Path, prompts_dir: Path
) -> PromptMessageDoc:
    if message.file is None:
        return PromptMessageDoc(
            role=message.role, source="inline", file=None, content=message.text or ""
        )
    try:
        target = resolve_template_file(prompts_dir, prompt_path, message.file)
        content = target.read_text(encoding="utf-8")
    except (HTTPException, OSError, UnicodeDecodeError) as e:
        logger.warning("Template %r of %s is not readable: %s", message.file, prompt_path, e)
        return PromptMessageDoc(
            role=message.role, source="file", file=message.file, content="", readable=False
        )
    return PromptMessageDoc(
        role=message.role, source="file", file=message.file, content=content, readable=True
    )


def build_tree(prompts_dir: Path) -> PromptTreeResponse:
    """Every ``<lang>/<agent>/prompt.yaml`` under *prompts_dir*.

    A file that does not parse is listed with ``ok=False`` and a reason rather
    than omitted or raised: one broken prompt must not hide the other seven,
    and an operator who cannot see a broken prompt in the console cannot fix it
    there either.
    """
    base = Path(prompts_dir)
    if not base.is_dir():
        logger.warning("No prompts directory at %s", base)
        return PromptTreeResponse(languages=[])

    languages: list[PromptTreeLanguage] = []
    for language_dir in sorted(p for p in base.iterdir() if p.is_dir()):
        entries: list[PromptTreeEntry] = []
        for agent_dir in sorted(p for p in language_dir.iterdir() if p.is_dir()):
            prompt_path = agent_dir / "prompt.yaml"
            if not prompt_path.is_file():
                continue
            entries.append(_tree_entry(agent_dir.name, prompt_path, base))
        if entries:
            languages.append(PromptTreeLanguage(lang=language_dir.name, prompts=entries))

    return PromptTreeResponse(languages=languages)


def _tree_entry(agent: str, prompt_path: Path, prompts_dir: Path) -> PromptTreeEntry:
    relative = prompt_path.relative_to(prompts_dir).as_posix()
    try:
        meta = read_prompt_meta(prompt_path, prompts_dir)
    except HTTPException as e:
        return PromptTreeEntry(
            agent=agent, file=relative, ok=False, error=str(e.detail), variants=[]
        )
    return PromptTreeEntry(
        agent=agent,
        file=relative,
        name=meta.name,
        variants=[variant.name for variant in meta.variants],
        ok=True,
    )


def build_write_set(
    request: PromptSaveRequest, prompt_path: Path, prompts_dir: Path
) -> dict[Path, str]:
    """Validate *request* and turn it into ``{path: text}``, touching nothing.

    Validation happens here, before any caller reaches ``write_all``, which is
    how "a multi-file apply with one invalid file writes nothing at all"
    (master spec §13) is satisfied -- by ordering, not by rollback.

    Raises:
        HTTPException 422: the document is not a usable ``PromptDefinition``,
            or ``default_variant`` names no variant.
        HTTPException 400/404: a ``file`` message points outside ``prompts_dir``,
            at a disallowed suffix, or at a file that does not exist. Phase 4a
            never creates a file.
    """
    base = Path(prompts_dir)
    files: dict[Path, str] = {}

    document: dict[str, Any] = {
        "name": request.name,
        "summary": request.summary,
        "description": request.description,
        "default_model": request.default_model,
        "default_variant": request.default_variant,
        "variants": [],
    }

    for variant in request.variants:
        messages: list[dict[str, Any]] = []
        for message in variant.messages:
            if message.source == "file":
                if not message.file:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail="A file-backed message must name a file",
                    )
                # Raises 400/404 when it escapes, is disallowed, or is absent.
                target = resolve_template_file(base, prompt_path, message.file)
                files[target] = message.content
                messages.append({"role": message.role, "file": message.file})
            else:
                messages.append({"role": message.role, "text": message.content})

        document["variants"].append(
            {
                "name": variant.name,
                "description": variant.description,
                "model": variant.model,
                "vars": {key: prune_none(decl.model_dump()) for key, decl in variant.vars.items()},
                "messages": messages,
            }
        )

    _validate_document(document)

    files[Path(prompt_path)] = document_to_yaml(
        document, header=schema_header(Path(prompt_path), base)
    )
    return files


def _validate_document(document: dict[str, Any]) -> None:
    """Refuse a document the runtime could not load."""
    try:
        definition = PromptDefinition.model_validate(prune_none(document))
    except ValidationError as e:
        fields = ", ".join(
            sorted({".".join(str(p) for p in err["loc"]) or "(root)" for err in e.errors()})
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"This is not a usable prompt definition: {fields}",
        ) from e

    names = {variant.name for variant in definition.variants}
    if definition.default_variant not in names:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"default_variant {definition.default_variant!r} names no variant. "
                f"Available: {', '.join(sorted(names)) or 'none'}"
            ),
        )
