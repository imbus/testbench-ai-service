"""Args, per-run options and the result summary of the coverage checker."""

import pytest
from pydantic import ValidationError

from testbench_ai_service.agents.coverage_checker.model import (
    AspectCoverage,
    CoverageCheckerArgs,
    CoverageResult,
    resolve_run_options,
)
from testbench_ai_service.utils.traceability.models import Aspect

ARGS = CoverageCheckerArgs()


def test_without_vars_the_args_apply():
    options = resolve_run_options(None, ARGS)

    assert options.write_review_comments is True
    assert options.counting_spec_status == frozenset({"InReview", "Released"})


def test_string_false_disables_writing():
    assert (
        resolve_run_options({"write_review_comments": "false"}, ARGS).write_review_comments is False
    )


def test_an_empty_var_counts_as_unset():
    assert resolve_run_options({"write_review_comments": ""}, ARGS).write_review_comments is True


def test_the_work_view_counts_unreleased_sets_too():
    options = resolve_run_options({"coverage_view": "work"}, ARGS)

    assert options.counting_spec_status == frozenset(
        {"Planned", "InProgress", "InReview", "Released"}
    )


@pytest.mark.parametrize(
    "prompt_vars", [{"coverage_view": "all"}, {"write_review_comments": "maybe"}]
)
def test_invalid_vars_are_rejected(prompt_vars):
    with pytest.raises(ValidationError):
        resolve_run_options(prompt_vars, ARGS)


def test_unknown_args_are_rejected():
    with pytest.raises(ValidationError):
        CoverageCheckerArgs(max_aspect=3)


def test_the_summary_counts_each_status():
    aspect = Aspect(id="A1", statement="s", kind="negative", source_quote="q")
    result = CoverageResult(
        requirement_key="REQ-42",
        aspects=[
            AspectCoverage(aspect=aspect, status="covered"),
            AspectCoverage(aspect=aspect, status="weak", weak_reason="only_partial"),
            AspectCoverage(aspect=aspect, status="missing"),
            AspectCoverage(aspect=aspect, status="missing"),
        ],
        sets_without_evidence=[],
        reduced_mode=False,
        incomplete=False,
    )

    assert result.summary() == "4 aspects: 1 covered, 1 weak, 2 missing"
