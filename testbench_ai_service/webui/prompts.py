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

from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml
from fastapi import HTTPException, status
from pydantic import BaseModel, ValidationError

from testbench_ai_service.config import AppConfig
from testbench_ai_service.log import logger
from testbench_ai_service.models.language import LanguageOption
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
    PromptUsage,
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


def resolve_template_target(prompts_dir: Path, prompt_path: Path, name: str) -> Path:
    """Where a *new* template called *name* would be created.

    Creation is confined to one path segment in the prompt's own directory
    (design D7), so "create a directory" never enters the design. Referencing an
    existing template elsewhere under ``prompts_dir`` is unaffected -- that still
    goes through :func:`resolve_template_file`.

    The suffix allowlist is applied to the RESOLVED path and before anything is
    stat'ed, exactly as ``resolve_template_file`` does it, so a refused
    extension is refused whether or not the file happens to exist.

    Raises:
        HTTPException 400: *name* is empty, is not a single path segment, or is
            not an allowlisted template suffix.
    """
    if not name.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Empty path is not allowed"
        )
    candidate = Path(name)
    if candidate.is_absolute() or len(candidate.parts) != 1 or name in {".", ".."}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"A new template file must be a plain file name in the prompt's own "
                f"directory, not {name!r}."
            ),
        )
    target = resolve_within(Path(prompts_dir), Path(prompt_path).parent / candidate)
    _require_template_suffix(target)
    return target


def _previous_template_refs(prompt_path: Path, prompts_dir: Path) -> set[Path]:
    """Which templates the prompt referenced **on disk**, before this save.

    Read from the file rather than taken from the request: a client-supplied
    "these were the previous files" list would let the browser nominate any
    contained file for deletion (design D9).
    """
    from testbench_ai_service.webui.template_refs import message_refs  # noqa: PLC0415

    try:
        document = yaml.safe_load(Path(prompt_path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        return set()

    refs: set[Path] = set()
    for ref in message_refs(document):
        try:
            refs.add(resolve_template_file(Path(prompts_dir), Path(prompt_path), ref))
        except HTTPException:
            continue
    return refs


def _plan_deletions(
    prompt_path: Path, prompts_dir: Path, previous_refs: set[Path], surviving: set[Path]
) -> tuple[list[Path], str | None]:
    """Which templates this save orphans, and why it might delete none.

    All three conditions of design 5.5 must hold: the file was referenced on
    disk before the save, is not referenced after it, and is referenced by no
    other prompt anywhere under ``prompts_dir``.

    *previous_refs* is taken as a parameter -- :func:`build_write_set` already
    computed it (as ``previous_refs``) for the existing-but-unowned check, and
    nothing is written to disk in between, so recomputing it here would be a
    redundant re-read and re-parse of the same file on every save.
    """
    from testbench_ai_service.webui.template_refs import scan_template_references  # noqa: PLC0415

    candidates = previous_refs - surviving
    if not candidates:
        return [], None

    scan = scan_template_references(Path(prompts_dir))
    if scan.blocked_by is not None:
        return [], (
            f"No file was deleted: {scan.blocked_by} could not be parsed, so the console "
            f"cannot tell which templates are still in use. Repair it, then save again."
        )

    # prompt_path is resolved by every caller (resolve_prompt_file ->
    # resolve_within -> Path.resolve()), but prompts_dir need not be --
    # config.toml's prompts_dir only has to exist, not be absolute. Without
    # resolving it here too, relative_to raises ValueError for a relative
    # prompts_dir, turning an ordinary save into a 500 (see _display_name's
    # sibling guard at line ~173, which the try/except pattern comes from --
    # here it can't raise at all, so no try/except is needed instead of one
    # around the resolve).
    own = Path(prompt_path).relative_to(Path(prompts_dir).resolve()).as_posix()
    deletes = []
    for candidate in sorted(candidates, key=str):
        holders = [name for name in scan.references.get(candidate, []) if name != own]
        if not holders:
            deletes.append(candidate)
    return deletes, None


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


def _declared_file(block: Any) -> Any:
    """The ``prompt.file`` value declared in one agent block, or ``None``."""
    if isinstance(block, dict) and isinstance(block.get("prompt"), dict):
        return block["prompt"].get("file")
    return None


def _global_usages(
    agents: Any, language: str, matches: Callable[[str, Any], bool]
) -> list[PromptUsage]:
    """Usages from the top-level ``[agents]`` table."""
    if not isinstance(agents, dict):
        return []
    return [
        PromptUsage(agent=str(key), project=None)
        for key, block in agents.items()
        if matches(language, _declared_file(block))
    ]


def _project_usages(
    projects: Any, language: str, matches: Callable[[str, Any], bool]
) -> list[PromptUsage]:
    """Usages from every ``[projects.<name>.agents]`` table.

    Each project resolves against its OWN ``language`` override when it
    declares one, otherwise the global *language* -- matching what
    ``AppConfig.validate_prompt_paths`` does at boot (design 5.3/D2).
    """
    if not isinstance(projects, dict):
        return []
    usages: list[PromptUsage] = []
    for project_name, project_block in projects.items():
        if not isinstance(project_block, dict):
            continue
        project_language = str(project_block.get("language") or language)
        project_agents = project_block.get("agents")
        if not isinstance(project_agents, dict):
            continue
        usages.extend(
            PromptUsage(agent=str(key), project=str(project_name))
            for key, block in project_agents.items()
            if matches(project_language, _declared_file(block))
        )
    return usages


def _usages(prompt_path: Path, prompts_dir: Path, on_disk: dict[str, Any]) -> list[PromptUsage]:
    """Which config keys resolve to *prompt_path*.

    Matched on RESOLVED paths, never on the directory's name: a fork's
    ``<agent>__<slug>`` directory is cosmetic, and a convention parsed as data
    becomes a lie the first time someone renames a directory by hand (D4).
    """

    def matches(lang: str, declared: Any) -> bool:
        if not isinstance(declared, str) or not declared.strip():
            return False
        try:
            return resolve_prompt_file(prompts_dir, lang, declared) == prompt_path
        except HTTPException:
            return False

    # An absent `language` key is not "no language" -- it is AppConfig's own
    # default (LanguageOption.GERMAN), the same value a config.toml that never
    # mentions `language` boots with. Falling back to "" here would make
    # resolve_prompt_file refuse `resolve_within(base, "")` outright (its own
    # empty-path guard), so a bare "explainer/prompt.yaml" declaration -- the
    # normal, unprefixed spelling -- would never match anything.
    language = str(on_disk.get("language") or LanguageOption.GERMAN.value)
    return _global_usages(on_disk.get("agents"), language, matches) + _project_usages(
        on_disk.get("projects"), language, matches
    )


def build_tree(prompts_dir: Path, on_disk: dict[str, Any] | None = None) -> PromptTreeResponse:
    """Every ``<lang>/<agent>/prompt.yaml`` under *prompts_dir*.

    A file that does not parse is listed with ``ok=False`` and a reason rather
    than omitted or raised: one broken prompt must not hide the other seven,
    and an operator who cannot see a broken prompt in the console cannot fix it
    there either.

    *on_disk* is the config's raw ``[testbench-ai-service]`` table, used only to
    label each entry's ``used_by``. It is optional, and ``None`` is treated the
    same as ``{}``: an unreadable ``config.toml`` must not cost the operator the
    tree itself, which is how they would reach a broken prompt to fix it.
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
            entries.append(_tree_entry(agent_dir.name, prompt_path, base, on_disk or {}))
        if entries:
            languages.append(PromptTreeLanguage(lang=language_dir.name, prompts=entries))

    return PromptTreeResponse(languages=languages)


def _tree_entry(
    agent: str, prompt_path: Path, prompts_dir: Path, on_disk: dict[str, Any]
) -> PromptTreeEntry:
    relative = prompt_path.relative_to(prompts_dir).as_posix()
    used_by = _usages(prompt_path, prompts_dir, on_disk)
    try:
        meta = read_prompt_meta(prompt_path, prompts_dir)
    except HTTPException as e:
        return PromptTreeEntry(
            agent=agent, file=relative, ok=False, error=str(e.detail), variants=[], used_by=used_by
        )
    return PromptTreeEntry(
        agent=agent,
        file=relative,
        name=meta.name,
        variants=[variant.name for variant in meta.variants],
        ok=True,
        used_by=used_by,
    )


def _already_on_disk(target: Path, text: str) -> bool:
    """True when *target* already holds exactly what a save would stage.

    Read as **bytes**, never through text mode, and compared two ways:

    * byte-for-byte against what :func:`~testbench_ai_service.webui.multi_write._stage`
      would write (UTF-8, ``newline=""``), and
    * against the on-disk bytes decoded the way ``_message_doc`` decoded them
      when the document loaded -- ``read_text``, i.e. universal newlines.

    The second comparison is what makes an **untouched CRLF** template compare
    equal to itself. Its bytes reach the browser as ``\\n`` and come back as
    ``\\n``, so a byte-only check would call the file "changed" and rewrite
    every line ending in it -- reintroducing for untouched files exactly the
    CRLF->LF rewrite design §2 ring-fenced as an out-of-scope leftover.

    An unreadable target counts as "changed": the caller should attempt the
    write and report the real failure rather than silently skip it.
    """
    try:
        raw = target.read_bytes()
    except OSError:
        return False
    if raw == text.encode("utf-8"):
        return True
    try:
        decoded = raw.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return decoded.replace("\r\n", "\n").replace("\r", "\n") == text


def _resolve_or_create_target(
    base: Path,
    prompt_path: Path,
    name: str,
    text: str,
    previous_refs: set[Path],
    created: set[Path],
) -> Path:
    """Resolve a file-backed message's target, creating it if it is new.

    An existing, previously-unreferenced file is refused only when this save
    would actually **change** it (design D9 guards against one prompt
    clobbering another's file, not against pointing at one -- design 3.6 and
    D7 both permit a message to legitimately reference an existing shared
    template). A message repeating a shared template's current content
    byte-for-byte is not a clobber and is not refused.

    Raises:
        HTTPException 400/404: *name* escapes *base*, carries a disallowed
            suffix, or (for a new file) names more than one path segment.
        HTTPException 409: *name* already exists on disk, this prompt did not
            previously reference it, and *text* differs from what is already
            there -- saving would overwrite a file that belongs to something
            else.
    """
    try:
        target = resolve_template_file(base, prompt_path, name)
    except HTTPException as e:
        if e.status_code != status.HTTP_404_NOT_FOUND:
            raise
        # Not there yet: this is a creation. Confined to one segment in the
        # prompt's own directory (D7).
        target = resolve_template_target(base, prompt_path, name)
        created.add(target)

    if target.exists() and target not in previous_refs and not _already_on_disk(target, text):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"{name!r} already exists and belongs to another prompt. Saving would "
                f"overwrite it with this message's body. Point this message at a "
                f"different file, or make its content match what is already there."
            ),
        )
    return target


class WritePlan(BaseModel):
    """What a save would do, computed without touching anything.

    ``writes`` is text only. A save always writes what the editor holds; the
    ``bytes`` entries :func:`~testbench_ai_service.webui.multi_write.write_all`
    accepts exist solely for the fork's faithful copy, which builds its own set.
    """

    writes: dict[Path, str] = {}
    #: The subset of ``writes`` that does not exist yet.
    creates: set[Path] = set()
    deletes: list[Path] = []
    #: Why no deletion was planned, when the tree scan could not be trusted.
    deletions_skipped: str | None = None


def build_write_set(request: PromptSaveRequest, prompt_path: Path, prompts_dir: Path) -> WritePlan:
    """Validate *request* and turn it into a :class:`WritePlan`, touching nothing.

    Validation happens here, before any caller reaches ``write_all``, which is
    how "a multi-file apply with one invalid file writes nothing at all"
    (master spec §13) is satisfied -- by ordering, not by rollback.

    Only targets whose on-disk bytes actually differ are returned: a save that
    changes the prompt's name must not rewrite (and back up, and re-line-end)
    every template the document merely references. See :func:`_already_on_disk`.

    Raises:
        HTTPException 422: the document is not a usable ``PromptDefinition``,
            ``default_variant`` names no variant, or a variant has no messages.
        HTTPException 400: a ``file`` message points outside ``prompts_dir``, at
            a disallowed suffix, or (for a new file) names more than one path
            segment.
        HTTPException 409: two messages reference the same template file with
            different content (a file has one body); a file-backed message
            arrived with ``readable: false`` -- its ``content`` is the empty
            placeholder the loader substituted, not the file's body; or a
            message names a file that already exists, that this prompt did
            not previously reference, and whose content this save would
            actually change.
    """
    base = Path(prompts_dir)
    previous_refs = _previous_template_refs(prompt_path, base)
    created: set[Path] = set()
    #: Every file-backed body, before the unchanged ones are filtered out.
    #: Kept separate from the final write set so the "one file, one body"
    #: check below still sees a second message pointing at a template the
    #: first one left unchanged.
    bodies: dict[Path, str] = {}

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
                if not message.readable:
                    # The loader substitutes content="" for a template it could
                    # not read or decode (a latin-1 file, say). Writing that
                    # back would truncate the real file to nothing -- silently,
                    # because a save changing only the prompt's NAME still
                    # carries every template body along with it. Design §5.1
                    # sanctions surfacing a broken reference, not overwriting
                    # it. Refuse, and name what the operator has to fix first.
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=(
                            f"The template file {message.file!r} could not be read when "
                            f"this prompt was loaded, so the editor is holding an empty "
                            f"body for it, not its real text. Saving would overwrite the "
                            f"file with nothing. Repair the file on disk -- check that it "
                            f"exists and is valid UTF-8 -- then reload this prompt and "
                            f"save again."
                        ),
                    )
                target = _resolve_or_create_target(
                    base, prompt_path, message.file, message.content, previous_refs, created
                )
                existing = bodies.get(target)
                if existing is not None and existing != message.content:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=(
                            f"Two messages give different content for the same template "
                            f"file {message.file!r}. A file has one body: point one of "
                            f"them at a different file, or make the two bodies identical."
                        ),
                    )
                bodies[target] = message.content
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

    plan = WritePlan(creates=created)
    for target, text in bodies.items():
        if target in created or not _already_on_disk(target, text):
            plan.writes[target] = text

    yaml_text = document_to_yaml(document, header=schema_header(Path(prompt_path), base))
    if not _already_on_disk(Path(prompt_path), yaml_text):
        plan.writes[Path(prompt_path)] = yaml_text

    plan.deletes, plan.deletions_skipped = _plan_deletions(
        Path(prompt_path), base, previous_refs, set(bodies)
    )
    return plan


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

    empty = sorted(v.name for v in definition.variants if not v.messages)
    if empty:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(f"Every variant needs at least one message. Empty: {', '.join(empty)}"),
        )
