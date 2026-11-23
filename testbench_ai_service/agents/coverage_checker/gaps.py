"""Step ``gaps``: why each weak or missing aspect is open, and a test that would close it.

One call covers all open aspects. The model sees each aspect with the evidence that
exists and the titles of the linked sets, not the whole context.
"""

from testbench_ai_service.agents.coverage_checker.model import AspectCoverage, GapList
from testbench_ai_service.models.agent import AgentData
from testbench_ai_service.utils.traceability.models import AskStep

STEP = "gaps"


class GapsData(AgentData):
    """Template variables of the ``gaps`` step."""

    requirement: str
    gaps: str
    test_case_sets: str


def render_gaps(coverages: list[AspectCoverage]) -> str:
    """The open aspects with their status and the evidence that exists for them."""
    blocks = []
    for coverage in coverages:
        if coverage.status == "covered":
            continue
        aspect = coverage.aspect
        lines = [f"{aspect.id} [{aspect.kind}] {aspect.statement}"]
        status = coverage.status
        if coverage.weak_reason:
            status += f" ({coverage.weak_reason})"
        lines.append(f"  status: {status}")
        lines.extend(
            f"  evidence: {item.test_case_key} in set {item.set_key} ({item.strength}): "
            f"{item.evidence}"
            for item in coverage.evidence
        )
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


async def explain_gaps(
    ask: AskStep, requirement: str, coverages: list[AspectCoverage], set_titles: list[str]
) -> list[AspectCoverage]:
    """Attach a gap reason and a suggested test to each weak or missing aspect.

    Explanations for covered or unknown aspects are ignored; an open aspect the model
    skipped stays without one.

    Raises:
        StructuredOutputError: The answer was not valid JSON even after the repair retry.
    """
    if all(coverage.status == "covered" for coverage in coverages):
        return coverages
    answer = await ask(
        STEP,
        GapList,
        GapsData(
            requirement=requirement,
            gaps=render_gaps(coverages),
            test_case_sets="\n".join(f"- {title}" for title in set_titles) or "(none)",
        ),
    )
    by_id = {gap.aspect_id.strip().upper(): gap for gap in answer.gaps}
    explained = []
    for coverage in coverages:
        gap = by_id.get(coverage.aspect.id)
        if coverage.status != "covered" and gap is not None:
            explained.append(
                coverage.model_copy(
                    update={"gap_reason": gap.gap_reason, "suggested_test": gap.suggested_test}
                )
            )
        else:
            explained.append(coverage)
    return explained
