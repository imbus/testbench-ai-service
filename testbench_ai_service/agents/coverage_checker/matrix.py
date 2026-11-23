"""The coverage matrix: one status per aspect, by fixed rules.

The model reads the tests; the code decides what counts. An aspect is covered only
by full evidence from a set whose specification state counts, so a test that is
not released yet, or that only touches the aspect, never reads as coverage.
"""

from dataclasses import dataclass

from testbench_ai_service.agents.coverage_checker.model import (
    AspectCoverage,
    CoverageEvidence,
    SetWithoutEvidence,
)
from testbench_ai_service.utils.traceability.models import Aspect, AspectEvidence


@dataclass(frozen=True)
class SetResult:
    """What the interpretation found in one linked set."""

    set_key: str
    spec_status: str
    has_test_cases: bool
    #: ``None`` when the set could not be interpreted.
    evidence: list[AspectEvidence] | None


def _coverage(
    aspect: Aspect,
    evidence: list[CoverageEvidence],
    status_of: dict[str, str],
    counting_spec_status: frozenset[str],
) -> AspectCoverage:
    if any(
        item.strength == "full" and status_of[item.set_key] in counting_spec_status
        for item in evidence
    ):
        return AspectCoverage(aspect=aspect, status="covered", evidence=evidence)
    if evidence:
        reason = (
            "set_not_released"
            if any(item.strength == "full" for item in evidence)
            else "only_partial"
        )
        return AspectCoverage(aspect=aspect, status="weak", weak_reason=reason, evidence=evidence)
    return AspectCoverage(aspect=aspect, status="missing")


def build_matrix(
    aspects: list[Aspect],
    set_results: list[SetResult],
    counting_spec_status: frozenset[str],
) -> tuple[list[AspectCoverage], list[SetWithoutEvidence]]:
    """One coverage row per aspect, in aspect order, and the sets that prove nothing."""
    status_of = {result.set_key: result.spec_status for result in set_results}
    by_aspect: dict[str, list[CoverageEvidence]] = {aspect.id: [] for aspect in aspects}
    for result in set_results:
        for item in result.evidence or []:
            if item.aspect_id in by_aspect:
                by_aspect[item.aspect_id].append(
                    CoverageEvidence(
                        set_key=result.set_key,
                        test_case_key=item.test_case_key,
                        strength=item.strength,
                        evidence=item.evidence,
                    )
                )

    coverages = [
        _coverage(aspect, by_aspect[aspect.id], status_of, counting_spec_status)
        for aspect in aspects
    ]

    without: list[SetWithoutEvidence] = []
    for result in set_results:
        if result.evidence is None:
            without.append(
                SetWithoutEvidence(set_key=result.set_key, reason="interpretation_failed")
            )
        elif not result.has_test_cases:
            without.append(SetWithoutEvidence(set_key=result.set_key, reason="no_test_cases"))
        elif not result.evidence:
            without.append(SetWithoutEvidence(set_key=result.set_key, reason="no_matching_aspect"))
    return coverages, without
