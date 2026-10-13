"""Step ``interpretation``: which linked test case proves which aspect, and how well.

The model reads one set at a time; a set with more test cases than fit one call is
read in batches with the full aspect list each time. Every answer names an aspect
and a test case, so the batches merge without loss. The code drops evidence for
aspects or test cases that do not exist and keeps the stronger of two answers for
the same pair.
"""

from collections.abc import Iterable
from typing import TypeVar

from testbench_ai_service.models.agent import AgentData
from testbench_ai_service.utils.traceability.models import (
    AskStep,
    Aspect,
    AspectEvidence,
    LinkedSet,
    SetInterpretation,
    TestCase,
)

STEP = "interpretation"

X = TypeVar("X")


class InterpretationData(AgentData):
    """Template variables of the ``interpretation`` step."""

    requirement: str
    aspects: str
    test_case_set: str
    test_cases: str


def render_aspects(aspects: list[Aspect]) -> str:
    return "\n".join(f"{aspect.id} [{aspect.kind}] {aspect.statement}" for aspect in aspects)


def render_test_case_set(linked_set: LinkedSet) -> str:
    return "\n".join(
        [
            f"{linked_set.title} ({linked_set.path})",
            f"Specification status: {linked_set.spec_status}",
            f"Description: {linked_set.description or '(none)'}",
        ]
    )


def render_test_case(test_case: TestCase) -> str:
    """A test case as the model reads it: parameters, then one line per call."""
    lines = [f"Test case {test_case.key}"]
    if test_case.parameters:
        values = ", ".join(f"{name}={value}" for name, value in test_case.parameters.items())
        lines.append(f"  parameters: {values}")
    for call in test_case.calls:
        arguments = ", ".join(f"{name}={value}" for name, value in call.arguments.items())
        marker = " [check]" if call.check else ""
        lines.append(f"  {call.phase}: {call.keyword}({arguments}){marker}")
    if not test_case.calls:
        lines.append("  (no test steps)")
    return "\n".join(lines)


def batches(items: list[X], size: int) -> list[list[X]]:
    return [items[start : start + size] for start in range(0, len(items), size)]


def validate_evidence(
    evidence: Iterable[AspectEvidence], aspect_ids: list[str], test_case_keys: set[str]
) -> list[AspectEvidence]:
    """Drop evidence for unknown aspects or test cases; keep the stronger per pair.

    Aspect IDs are compared trimmed and upper-cased, test case keys trimmed.

    Returns:
        The evidence in aspect order, then by test case key.
    """
    order = {aspect_id: index for index, aspect_id in enumerate(aspect_ids)}
    best: dict[tuple[str, str], AspectEvidence] = {}
    for item in evidence:
        aspect_id = item.aspect_id.strip().upper()
        key = item.test_case_key.strip()
        if aspect_id not in order or key not in test_case_keys:
            continue
        checked = item.model_copy(update={"aspect_id": aspect_id, "test_case_key": key})
        current = best.get((aspect_id, key))
        if current is None or (current.strength == "partial" and checked.strength == "full"):
            best[(aspect_id, key)] = checked
    return sorted(best.values(), key=lambda e: (order[e.aspect_id], e.test_case_key))


async def interpret_set(
    ask: AskStep,
    requirement: str,
    aspects: list[Aspect],
    linked_set: LinkedSet,
    batch_size: int,
) -> list[AspectEvidence]:
    """Ask the model which of the set's test cases prove which aspect.

    Args:
        ask: Asks one prompt step.
        requirement: The rendered requirement.
        aspects: The validated aspects.
        linked_set: The set with its linked test cases.
        batch_size: Most test cases sent in one call.

    Raises:
        StructuredOutputError: An answer was not valid JSON even after the repair retry.
    """
    if not linked_set.test_cases:
        return []
    collected: list[AspectEvidence] = []
    for batch in batches(linked_set.test_cases, batch_size):
        answer = await ask(
            STEP,
            SetInterpretation,
            InterpretationData(
                requirement=requirement,
                aspects=render_aspects(aspects),
                test_case_set=render_test_case_set(linked_set),
                test_cases="\n\n".join(render_test_case(test_case) for test_case in batch),
            ),
        )
        collected.extend(answer.evidence)
    return validate_evidence(
        collected,
        [aspect.id for aspect in aspects],
        {test_case.key for test_case in linked_set.test_cases},
    )
