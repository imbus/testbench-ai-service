"""Step ``aspects``: split a requirement into testable statements.

The model decides what a testable aspect is; the code decides which answers count.
An aspect must quote the requirement text, so aspects the model adds from experience
("login should also be rate limited") fall out, and duplicates and overflow are cut.
"""

from testbench_ai_service.log import logger
from testbench_ai_service.models.agent import AgentData
from testbench_ai_service.utils.html_utils import visible_text
from testbench_ai_service.utils.rm_service import Requirement
from testbench_ai_service.utils.traceability.models import AskStep, Aspect, AspectList

STEP = "aspects"


class AspectsData(AgentData):
    """Template variables of the ``aspects`` step."""

    requirement: str
    max_aspects: str


class NoAspectsError(ValueError):
    """None of the model's aspects could be traced to the requirement text."""


def render_requirement(requirement: Requirement) -> str:
    """The requirement as the model reads it: reference, title, attributes, description."""
    lines = [f"{requirement.external_ref or requirement.key}: {requirement.title}"]
    attributes = [
        f"{label}: {value}"
        for label, value in (("status", requirement.status), ("priority", requirement.priority))
        if value
    ]
    if attributes:
        lines.append(" | ".join(attributes))
    description = visible_text(requirement.description or "")
    lines.append(f"Description: {description or '(none, only the title is known)'}")
    return "\n".join(lines)


def requirement_text(requirement: Requirement) -> str:
    """The text an aspect's quote must come from: the title and the visible description."""
    return f"{requirement.title}\n{visible_text(requirement.description or '')}"


def _normalized(text: str) -> str:
    return " ".join(text.casefold().split())


def validate_aspects(answer: AspectList, source_text: str, max_aspects: int) -> list[Aspect]:
    """Keep the aspects the text backs, without duplicates, numbered ``A1..An``.

    Args:
        answer: The model's aspects.
        source_text: The requirement's title and visible description.
        max_aspects: Upper bound on the aspects kept.

    Returns:
        The kept aspects in the model's order, renumbered.
    """
    source = _normalized(source_text)
    kept: list[Aspect] = []
    seen: set[str] = set()
    for aspect in answer.aspects:
        quote = _normalized(aspect.source_quote)
        if not quote or quote not in source:
            logger.debug(
                "Dropping aspect %r: its quote is not in the requirement", aspect.statement
            )
            continue
        statement = _normalized(aspect.statement)
        if statement in seen:
            continue
        seen.add(statement)
        kept.append(aspect)
    return [
        aspect.model_copy(update={"id": f"A{number}"})
        for number, aspect in enumerate(kept[:max_aspects], start=1)
    ]


async def decompose(ask: AskStep, requirement: Requirement, max_aspects: int) -> list[Aspect]:
    """Ask the model for the requirement's aspects and keep the valid ones.

    Raises:
        NoAspectsError: No aspect survived validation.
        StructuredOutputError: The answer was not valid JSON even after the repair retry.
    """
    answer = await ask(
        STEP,
        AspectList,
        AspectsData(requirement=render_requirement(requirement), max_aspects=str(max_aspects)),
    )
    aspects = validate_aspects(answer, requirement_text(requirement), max_aspects)
    if not aspects:
        raise NoAspectsError(
            f"None of the {len(answer.aspects)} aspects of requirement "
            f"'{requirement.external_ref or requirement.key}' quotes its text"
        )
    logger.debug(
        "Aspects of requirement '%s' (%d of %d kept): %s",
        requirement.external_ref or requirement.key,
        len(aspects),
        len(answer.aspects),
        [aspect.statement for aspect in aspects],
    )
    return aspects
