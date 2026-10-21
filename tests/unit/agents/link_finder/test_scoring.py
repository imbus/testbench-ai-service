"""Confidence rules: the code decides what the evidence is worth."""

import pytest

from testbench_ai_service.agents.link_finder.scoring import (
    confidence,
    covered_aspect_ids,
    rank_key,
)
from testbench_ai_service.utils.traceability.models import Aspect, AspectEvidence

ASPECTS = [
    Aspect(id=f"A{n}", statement=f"s{n}", kind="happy_path", source_quote="q") for n in range(1, 5)
]


def _evidence(*pairs):
    return [
        AspectEvidence(
            aspect_id=aspect_id, test_case_key=f"TC-{i}", strength=strength, evidence="e"
        )
        for i, (aspect_id, strength) in enumerate(pairs)
    ]


@pytest.mark.parametrize(
    ("pairs", "expected"),
    [
        ([("A1", "full"), ("A2", "partial")], "high"),  # 2 of 4 touched, ratio 0.5 reached
        ([("A1", "full")], "medium"),
        ([("A1", "full"), ("A1", "partial")], "medium"),  # one aspect, counted once
        ([("A1", "partial"), ("A2", "partial"), ("A3", "partial")], "low"),
        ([], None),
    ],
)
def test_confidence(pairs, expected):
    assert confidence(ASPECTS, _evidence(*pairs), 0.5, reduced_mode=False) == expected


@pytest.mark.parametrize(
    ("pairs", "expected"),
    [
        ([("A1", "full"), ("A2", "partial")], "medium"),
        ([("A1", "full")], "low"),
        ([("A1", "partial")], None),
    ],
)
def test_reduced_mode_lowers_by_one_level(pairs, expected):
    assert confidence(ASPECTS, _evidence(*pairs), 0.5, reduced_mode=True) == expected


def test_the_ratio_is_configurable():
    evidence = _evidence(("A1", "full"), ("A2", "full"))

    assert confidence(ASPECTS, evidence, 0.75, reduced_mode=False) == "medium"


def test_covered_aspects_keep_the_aspect_order():
    evidence = _evidence(("A3", "partial"), ("A1", "full"), ("A3", "full"))

    assert covered_aspect_ids(ASPECTS, evidence) == ["A1", "A3"]


def test_ranking_by_confidence_then_aspects_then_path():
    entries = [("medium", 3, "/b"), ("high", 1, "/z"), ("medium", 3, "/a"), ("medium", 4, "/c")]

    assert sorted(entries, key=lambda e: rank_key(*e)) == [
        ("high", 1, "/z"),
        ("medium", 4, "/c"),
        ("medium", 3, "/a"),
        ("medium", 3, "/b"),
    ]
