"""Who points at a prompt variant by name.

A variant is referenced from **two** places, both free strings resolved at
runtime (design §3.5):

- ``agents.<key>.prompt.variant``           -- ``PromptConfig.variant``
- ``projects.<name>.agents.<key>.prompt.variant`` -- ``ProjectPromptConfig.variant``

``get_prompt_variant`` falls back to ``default_variant`` when a name does not
match, so an orphaned reference is a wrong-output bug with no error anywhere.
Renaming or removing a variant therefore has to be checked against both tables.

Reads the **on-disk** config table, for the same reason ``declared_prompt_file``
does: the console's forms show ``GET /config``'s ``disk``, so a guard resolved
from the running config would refuse or permit based on a state the operator
cannot see. ``disk`` is unvalidated TOML, so every level is type-guarded -- a
bad shape must cost a check, not a 500.
"""

from typing import Any

from pydantic import BaseModel


class VariantRef(BaseModel):
    """One config key naming a prompt variant."""

    agent: str
    #: ``None`` for the global agents table, otherwise the project's raw name.
    project: str | None = None
    variant: str

    def label(self) -> str:
        """How the reference is named back to the operator."""
        return f"project {self.project!r}" if self.project else "the global agents table"


def _variant_of(agent_block: Any) -> str | None:
    if not isinstance(agent_block, dict):
        return None
    prompt = agent_block.get("prompt")
    if not isinstance(prompt, dict):
        return None
    variant = prompt.get("variant")
    return variant if isinstance(variant, str) and variant.strip() else None


def variant_references(agent_key: str, on_disk: dict[str, Any]) -> list[VariantRef]:
    """Every config key that names a variant of *agent_key*'s prompt."""
    refs: list[VariantRef] = []

    agents = on_disk.get("agents")
    if isinstance(agents, dict):
        variant = _variant_of(agents.get(agent_key))
        if variant is not None:
            refs.append(VariantRef(agent=agent_key, project=None, variant=variant))

    projects = on_disk.get("projects")
    if isinstance(projects, dict):
        for project_name, block in projects.items():
            if not isinstance(block, dict):
                continue
            project_agents = block.get("agents")
            if not isinstance(project_agents, dict):
                continue
            variant = _variant_of(project_agents.get(agent_key))
            if variant is not None:
                refs.append(VariantRef(agent=agent_key, project=str(project_name), variant=variant))

    return refs
