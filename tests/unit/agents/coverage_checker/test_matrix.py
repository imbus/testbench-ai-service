"""The coverage status of each aspect follows fixed rules, not a model's judgement."""

import pytest

from testbench_ai_service.agents.coverage_checker.matrix import SetResult, build_matrix
from testbench_ai_service.utils.traceability.models import Aspect, AspectEvidence

COUNTING = frozenset({"InReview", "Released"})
A1 = Aspect(id="A1", statement="Login succeeds", kind="happy_path", source_quote="q")


def _evidence(strength, key="TC-1", aspect_id="A1"):
    return AspectEvidence(aspect_id=aspect_id, test_case_key=key, strength=strength, evidence="e")


@pytest.mark.parametrize(
    ("results", "status", "weak_reason"),
    [
        ([SetResult("s1", "Released", True, [_evidence("full")])], "covered", None),
        ([SetResult("s1", "InReview", True, [_evidence("full")])], "covered", None),
        ([SetResult("s1", "Released", True, [_evidence("partial")])], "weak", "only_partial"),
        ([SetResult("s1", "InProgress", True, [_evidence("full")])], "weak", "set_not_released"),
        (
            [
                SetResult("s1", "Planned", True, [_evidence("full")]),
                SetResult("s2", "Released", True, [_evidence("partial", "TC-2")]),
            ],
            "weak",
            "set_not_released",
        ),
        (
            [
                SetResult("s1", "Planned", True, [_evidence("partial")]),
                SetResult("s2", "Released", True, [_evidence("full", "TC-2")]),
            ],
            "covered",
            None,
        ),
        ([SetResult("s1", "Released", True, [])], "missing", None),
        ([], "missing", None),
    ],
)
def test_status_rules(results, status, weak_reason):
    (coverage,), _ = build_matrix([A1], results, COUNTING)

    assert (coverage.status, coverage.weak_reason) == (status, weak_reason)


def test_evidence_keeps_the_set_it_came_from():
    (coverage,), _ = build_matrix(
        [A1], [SetResult("s1", "Released", True, [_evidence("full")])], COUNTING
    )

    assert [(e.set_key, e.test_case_key, e.strength) for e in coverage.evidence] == [
        ("s1", "TC-1", "full")
    ]


def test_sets_without_evidence_name_their_reason():
    _, without = build_matrix(
        [A1],
        [
            SetResult("empty", "Released", False, []),
            SetResult("unrelated", "Released", True, []),
            SetResult("failed", "Released", True, None),
            SetResult("useful", "Released", True, [_evidence("partial")]),
        ],
        COUNTING,
    )

    assert [(s.set_key, s.reason) for s in without] == [
        ("empty", "no_test_cases"),
        ("unrelated", "no_matching_aspect"),
        ("failed", "interpretation_failed"),
    ]


def test_every_aspect_gets_exactly_one_row_in_order():
    a2 = Aspect(id="A2", statement="Lock", kind="boundary", source_quote="q")

    coverages, _ = build_matrix(
        [A1, a2], [SetResult("s1", "Released", True, [_evidence("full", aspect_id="A2")])], COUNTING
    )

    assert [(c.aspect.id, c.status) for c in coverages] == [("A1", "missing"), ("A2", "covered")]
