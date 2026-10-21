"""Args, per-run options and the result summary of the link finder."""

import pytest
from pydantic import ValidationError

from testbench_ai_service.agents.link_finder.model import (
    LinkCandidate,
    LinkFinderArgs,
    LinkFinderResult,
    at_least,
    resolve_run_options,
)

ARGS = LinkFinderArgs()


def test_without_vars_the_args_apply():
    options = resolve_run_options(None, ARGS)

    assert (options.write_review_comments, options.min_confidence_for_comment) == (True, "low")


def test_vars_override_the_args():
    options = resolve_run_options(
        {"write_review_comments": "false", "min_confidence_for_comment": "high"}, ARGS
    )

    assert (options.write_review_comments, options.min_confidence_for_comment) == (False, "high")


def test_an_empty_var_counts_as_unset():
    options = resolve_run_options({"min_confidence_for_comment": ""}, ARGS)

    assert options.min_confidence_for_comment == "low"


def test_an_unknown_confidence_is_rejected():
    with pytest.raises(ValidationError):
        resolve_run_options({"min_confidence_for_comment": "certain"}, ARGS)


@pytest.mark.parametrize("ratio", [0, 1.5])
def test_the_ratio_must_be_a_share(ratio):
    with pytest.raises(ValidationError):
        LinkFinderArgs(high_confidence_ratio=ratio)


@pytest.mark.parametrize(
    ("level", "threshold", "expected"),
    [("high", "medium", True), ("medium", "medium", True), ("low", "medium", False)],
)
def test_at_least(level, threshold, expected):
    assert at_least(level, threshold) is expected


def test_summary():
    def candidate(level):
        return LinkCandidate(
            set_key=level,
            set_title="t",
            path="/p",
            spec_status="Released",
            confidence=level,
            covered_aspect_ids=["A1"],
            evidence=[],
            already_linked_to=[],
        )

    result = LinkFinderResult(
        requirement_key="REQ-42",
        aspects={},
        candidates=[candidate("high"), candidate("medium"), candidate("medium")],
        sets_screened=120,
        sets_detailed=9,
        reduced_mode=False,
        incomplete=False,
    )

    assert result.summary() == "3 candidates (1 high, 2 medium, 0 low) from 9 of 120 sets"
