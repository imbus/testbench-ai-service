"""Which prompt files still reference which template files.

A message template may be shared: ``resolve_template_file`` resolves a ``file:``
reference against the prompt YAML's own directory but checks containment against
``prompts_dir``, so ``../shared/common.jinja`` is legal and resolves the same way
at runtime. "Is this template still in use?" is therefore a question about the
whole tree, never about one document, and any deletion reasoning from a single
``prompt.yaml`` is wrong.

**A prompt that does not parse blocks every deletion.** Reading it as
"references nothing" would make its templates look orphaned and delete them, so
``blocked_by`` names the first such file and the caller must delete nothing at
all. Fail-safe rather than fail-closed: the save still writes, it just leaves
the orphan behind (design 5.5).

Parsing is deliberately tolerant. A file that is valid YAML but not a valid
``PromptDefinition`` still has its references counted -- it is a prompt someone
is midway through fixing, and its templates are no less in use for that.
"""

from pathlib import Path
from typing import Any

import yaml
from fastapi import HTTPException
from pydantic import BaseModel

from testbench_ai_service.log import logger
from testbench_ai_service.webui.prompts import resolve_template_file


class TemplateScan(BaseModel):
    """Every template reference under a prompts directory."""

    #: Resolved absolute template path -> the relative ``<lang>/<agent>/prompt.yaml``
    #: spellings that reference it.
    references: dict[Path, list[str]] = {}
    #: The first prompt file that failed to parse, relative to prompts_dir.
    #: Non-None means no deletion may be performed anywhere.
    blocked_by: str | None = None


def message_refs(document: Any) -> list[str]:
    """Every ``file:`` value in *document*, without validating its shape."""
    refs: list[str] = []
    if not isinstance(document, dict):
        return refs
    variants = document.get("variants")
    if not isinstance(variants, list):
        return refs
    for variant in variants:
        if not isinstance(variant, dict):
            continue
        messages = variant.get("messages")
        if not isinstance(messages, list):
            continue
        for message in messages:
            if not isinstance(message, dict):
                continue
            ref = message.get("file")
            if isinstance(ref, str) and ref.strip():
                refs.append(ref)
    return refs


def scan_template_references(prompts_dir: Path) -> TemplateScan:
    """Walk every ``<lang>/<agent>/prompt.yaml`` and resolve its template refs."""
    base = Path(prompts_dir)
    scan = TemplateScan()
    if not base.is_dir():
        return scan

    for language_dir in sorted(p for p in base.iterdir() if p.is_dir()):
        for agent_dir in sorted(p for p in language_dir.iterdir() if p.is_dir()):
            prompt_path = agent_dir / "prompt.yaml"
            if not prompt_path.is_file():
                continue
            relative = prompt_path.relative_to(base).as_posix()
            try:
                document = yaml.safe_load(prompt_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, yaml.YAMLError) as e:
                logger.warning("Prompt %s could not be parsed for the scan: %s", relative, e)
                if scan.blocked_by is None:
                    scan.blocked_by = relative
                continue

            for ref in message_refs(document):
                try:
                    target = resolve_template_file(base, prompt_path, ref)
                except HTTPException:
                    # Escapes prompts_dir, disallowed suffix, or is not there.
                    # Nothing on disk to protect, so nothing to record.
                    continue
                scan.references.setdefault(target, [])
                if relative not in scan.references[target]:
                    scan.references[target].append(relative)

    return scan
