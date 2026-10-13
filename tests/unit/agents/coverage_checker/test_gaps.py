"""Explaining the weak and missing aspects, one call for all of them."""

from testbench_ai_service.agents.coverage_checker.gaps import explain_gaps, render_gaps
from testbench_ai_service.agents.coverage_checker.model import (
    AspectCoverage,
    CoverageEvidence,
    GapExplanation,
    GapList,
    SuggestedTest,
)
from testbench_ai_service.utils.traceability.models import Aspect


def _aspect(aspect_id, statement):
    return Aspect(id=aspect_id, statement=statement, kind="negative", source_quote="q")


COVERED = AspectCoverage(aspect=_aspect("A1", "Login succeeds"), status="covered")
WEAK = AspectCoverage(
    aspect=_aspect("A2", "Lock after 3 failures"),
    status="weak",
    weak_reason="only_partial",
    evidence=[
        CoverageEvidence(
            set_key="s1", test_case_key="TC-1", strength="partial", evidence="fails 3 times"
        )
    ],
)
MISSING = AspectCoverage(aspect=_aspect("A3", "Behaviour after lock"), status="missing")


def _gap(aspect_id):
    normalized = aspect_id.strip().upper()
    return GapExplanation(
        aspect_id=aspect_id,
        gap_reason=f"why {normalized}",
        suggested_test=SuggestedTest(title=f"Test {normalized}", description="do it"),
    )


def test_only_open_aspects_are_rendered_with_their_evidence():
    rendered = render_gaps([COVERED, WEAK, MISSING])

    assert "A1" not in rendered
    assert "A2 [negative] Lock after 3 failures\n  status: weak (only_partial)" in rendered
    assert "  evidence: TC-1 in set s1 (partial): fails 3 times" in rendered
    assert "A3 [negative] Behaviour after lock\n  status: missing" in rendered


async def test_explanations_are_attached_to_open_aspects_only():
    calls = []

    async def ask(step, schema, agent_data):
        calls.append((step, schema, agent_data))
        return GapList(gaps=[_gap(" a3 "), _gap("A1"), _gap("A9")])

    result = await explain_gaps(ask, "REQ-42: Login", [COVERED, WEAK, MISSING], ["Login (/Auth)"])

    ((step, schema, agent_data),) = calls
    assert (step, schema) == ("gaps", GapList)
    assert agent_data["test_case_sets"] == "- Login (/Auth)"
    assert [(c.aspect.id, c.gap_reason) for c in result] == [
        ("A1", None),
        ("A2", None),
        ("A3", "why A3"),
    ]
    assert result[2].suggested_test.title == "Test A3"


async def test_nothing_is_asked_when_everything_is_covered():
    async def ask(step, schema, agent_data):
        raise AssertionError("must not be called")

    assert await explain_gaps(ask, "REQ-42", [COVERED], []) == [COVERED]
