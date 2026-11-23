"""Arguments, per-run options and results of the coverage checker."""

from collections import Counter
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, Field, TypeAdapter

from testbench_ai_service.models.agent import AgentData
from testbench_ai_service.utils.rm_service import RmServiceArgs
from testbench_ai_service.utils.traceability.models import Aspect, EvidenceStrength

CoverageView = Literal["release", "work"]
CoverageStatus = Literal["covered", "weak", "missing"]
WeakReason = Literal["only_partial", "set_not_released"]
NoEvidenceReason = Literal["no_test_cases", "no_matching_aspect", "interpretation_failed"]


class CoverageCheckerArgs(RmServiceArgs):
    """Arguments of the coverage checker, set in its ``args`` config table."""

    max_aspects: int = Field(default=12, gt=0, description="Keep at most this many aspects.")
    counting_spec_status: list[str] = Field(
        default=["InReview", "Released"],
        description="Specification states whose evidence counts in the release view.",
    )
    work_spec_status: list[str] = Field(
        default=["Planned", "InProgress", "InReview", "Released"],
        description="Specification states whose evidence counts in the work view.",
    )
    write_review_comments: bool = Field(
        default=True, description="Write the result into the linked sets' review comments."
    )
    max_parallel_sets: int = Field(
        default=4, gt=0, description="Sets interpreted and written at the same time."
    )
    max_test_cases_per_call: int = Field(
        default=20, gt=0, description="Test cases sent to the model in one call."
    )


class CoverageRunOptions(BaseModel):
    """What one run does, after the trigger's prompt vars are applied over the args."""

    write_review_comments: bool
    counting_spec_status: frozenset[str]


def resolve_run_options(
    prompt_vars: Mapping[str, Any] | None, args: CoverageCheckerArgs
) -> CoverageRunOptions:
    """Apply the prompt vars ``write_review_comments`` and ``coverage_view`` over the args.

    Empty values count as unset. Strings such as ``"false"`` are parsed, not taken
    as truthy.

    Raises:
        pydantic.ValidationError: A var holds a value it cannot take.
    """
    values = {name: value for name, value in (prompt_vars or {}).items() if value != ""}
    write = TypeAdapter(bool).validate_python(
        values.get("write_review_comments", args.write_review_comments)
    )
    view = TypeAdapter(CoverageView).validate_python(values.get("coverage_view", "release"))
    statuses = args.work_spec_status if view == "work" else args.counting_spec_status
    return CoverageRunOptions(write_review_comments=write, counting_spec_status=frozenset(statuses))


class SuggestedTest(BaseModel):
    """A sketch of a missing test, shaped like the generator's test idea."""

    title: str
    description: str


class CoverageEvidence(BaseModel):
    """Evidence for an aspect, with the set it comes from."""

    set_key: str
    test_case_key: str
    strength: EvidenceStrength
    evidence: str


class AspectCoverage(BaseModel):
    aspect: Aspect
    status: CoverageStatus
    weak_reason: WeakReason | None = None
    evidence: list[CoverageEvidence] = []
    gap_reason: str | None = None
    suggested_test: SuggestedTest | None = None


class SetWithoutEvidence(BaseModel):
    """A linked set that proves none of the aspects."""

    set_key: str
    reason: NoEvidenceReason


class CoverageResult(BaseModel):
    requirement_key: str
    aspects: list[AspectCoverage]
    sets_without_evidence: list[SetWithoutEvidence]
    #: Sets whose review comment was not written: locked by someone else, or the write failed.
    skipped_comments: list[str] = []
    reduced_mode: bool
    #: At least one linked set could not be interpreted.
    incomplete: bool
    #: No test case is linked to the requirement; nothing was checked or written.
    no_linked_tests: bool = False
    #: Set key to its path in the test structure, so the logged result reads on its own.
    set_paths: dict[str, str] = {}

    def summary(self) -> str:
        if self.no_linked_tests:
            return "no linked test cases"
        counts = Counter(coverage.status for coverage in self.aspects)
        return (
            f"{len(self.aspects)} aspects: {counts['covered']} covered, "
            f"{counts['weak']} weak, {counts['missing']} missing"
        )


class GapExplanation(BaseModel):
    """The model's explanation of one gap."""

    aspect_id: str
    gap_reason: str
    suggested_test: SuggestedTest


class GapList(BaseModel):
    gaps: list[GapExplanation]


class CoverageCheckerData(AgentData):
    """Template variables of the variant's ``messages``, which this agent leaves empty.

    Each step has its own data class; see ``CoverageChecker.STEP_DATA_CLASSES``.
    """
