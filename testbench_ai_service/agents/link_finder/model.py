"""Arguments, per-run options and results of the link finder."""

from collections import Counter
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, Field, TypeAdapter

from testbench_ai_service.models.agent import AgentData
from testbench_ai_service.utils.rm_service import RmServiceArgs
from testbench_ai_service.utils.traceability.models import AspectEvidence

Confidence = Literal["high", "medium", "low"]
Relevance = Literal["high", "medium", "low"]

#: Confidence levels from strongest to weakest; a level counts if it is at least the threshold.
CONFIDENCE_ORDER: tuple[Confidence, ...] = ("high", "medium", "low")


def at_least(confidence: Confidence, threshold: Confidence) -> bool:
    return CONFIDENCE_ORDER.index(confidence) <= CONFIDENCE_ORDER.index(threshold)


class LinkFinderArgs(RmServiceArgs):
    """Arguments of the link finder, set in its ``args`` config table."""

    max_aspects: int = Field(default=12, gt=0, description="Keep at most this many aspects.")
    prefilter_batch_size: int = Field(
        default=40, gt=0, description="Test case sets the prefilter sends to the model in one call."
    )
    max_sets_searched: int = Field(
        default=1000,
        gt=0,
        description="Refuse a requirement with more unlinked sets than this; each costs prefilter tokens.",
    )
    max_candidates: int = Field(
        default=15, gt=0, description="Most sets the prefilter passes on to the interpretation."
    )
    high_confidence_ratio: float = Field(
        default=0.5,
        gt=0,
        le=1,
        description="Share of the aspects a candidate must touch for confidence high.",
    )
    min_confidence_for_comment: Confidence = Field(
        default="low", description="Lowest confidence that gets a review comment."
    )
    write_review_comments: bool = Field(
        default=True, description="Write the candidates into their review comments."
    )
    max_parallel_sets: int = Field(
        default=4, gt=0, description="Model calls and comment writes running at the same time."
    )
    max_test_cases_per_call: int = Field(
        default=20, gt=0, description="Test cases sent to the model in one call."
    )


class LinkFinderRunOptions(BaseModel):
    """What one run does, after the trigger's prompt vars are applied over the args."""

    write_review_comments: bool
    min_confidence_for_comment: Confidence


def resolve_run_options(
    prompt_vars: Mapping[str, Any] | None, args: LinkFinderArgs
) -> LinkFinderRunOptions:
    """Apply the prompt vars ``write_review_comments`` and ``min_confidence_for_comment``.

    Empty values count as unset. Strings such as ``"false"`` are parsed, not taken
    as truthy.

    Raises:
        pydantic.ValidationError: A var holds a value it cannot take.
    """
    values = {name: value for name, value in (prompt_vars or {}).items() if value != ""}
    write = TypeAdapter(bool).validate_python(
        values.get("write_review_comments", args.write_review_comments)
    )
    threshold = TypeAdapter(Confidence).validate_python(
        values.get("min_confidence_for_comment", args.min_confidence_for_comment)
    )
    return LinkFinderRunOptions(write_review_comments=write, min_confidence_for_comment=threshold)


class TestCaseSetSummary(BaseModel):
    """What the prefilter sees of a set: no test steps."""

    __test__ = False

    key: str
    title: str
    path: str
    description_short: str
    spec_status: str


class PrefilterHit(BaseModel):
    """A set the prefilter thinks may test the requirement."""

    set_key: str
    #: How likely the model finds it; only used to choose when there are too many hits.
    relevance: Relevance = "medium"
    reason: str


class PrefilterAnswer(BaseModel):
    hits: list[PrefilterHit]


class PrefilterResult(BaseModel):
    hits: list[PrefilterHit]
    sets_screened: int
    #: At least one batch could not be screened; its sets were never looked at.
    incomplete: bool = False
    #: Keys of the sets in the batches that could not be screened.
    unscreened: list[str] = []


class LinkCandidate(BaseModel):
    set_key: str
    set_title: str
    path: str
    spec_status: str
    confidence: Confidence
    #: Aspects with at least one piece of evidence, in aspect order.
    covered_aspect_ids: list[str]
    evidence: list[AspectEvidence]
    #: Other requirements the set or one of its test cases is linked to.
    already_linked_to: list[str]


class LinkFinderResult(BaseModel):
    requirement_key: str
    #: The aspects as ``id -> statement``, so the logged result reads on its own.
    aspects: dict[str, str]
    #: Sorted by confidence, then by number of aspects touched.
    candidates: list[LinkCandidate]
    sets_screened: int
    sets_detailed: int
    #: Candidates without test cases, which prove nothing.
    empty_sets: list[str] = []
    #: Candidates whose interpretation failed.
    failed_sets: list[str] = []
    #: Candidates whose review comment should have been written but was not.
    skipped_comments: list[str] = []
    reduced_mode: bool
    #: A prefilter batch or a candidate could not be evaluated.
    incomplete: bool
    #: Set key to its path in the test structure.
    set_paths: dict[str, str] = {}

    def summary(self) -> str:
        counts = Counter(candidate.confidence for candidate in self.candidates)
        return (
            f"{len(self.candidates)} candidates ({counts['high']} high, {counts['medium']} medium, "
            f"{counts['low']} low) from {self.sets_detailed} of {self.sets_screened} sets"
        )


class LinkFinderData(AgentData):
    """Template variables of the variant's ``messages``, which this agent leaves empty.

    Each step has its own data class; see ``LinkFinder.STEP_DATA_CLASSES``.
    """
