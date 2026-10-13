"""The text of the review block and of the log report."""

from testbench_ai_service.agents.coverage_checker.formatting import (
    block_body,
    headings,
    render_report,
    render_set_block,
)
from testbench_ai_service.agents.coverage_checker.model import (
    AspectCoverage,
    CoverageEvidence,
    CoverageResult,
    SetWithoutEvidence,
    SuggestedTest,
)
from testbench_ai_service.models.language import LanguageOption
from testbench_ai_service.utils.i18n import load_translations
from testbench_ai_service.utils.traceability.models import Aspect
from testbench_ai_service.utils.traceability.review_writer import block_pattern

load_translations()


def _aspect(aspect_id, statement):
    return Aspect(id=aspect_id, statement=statement, kind="negative", source_quote="q")


def _evidence(set_key, key, strength):
    return CoverageEvidence(set_key=set_key, test_case_key=key, strength=strength, evidence="e")


def _result(**overrides):
    values = {
        "requirement_key": "REQ-42",
        "aspects": [
            AspectCoverage(
                aspect=_aspect("A1", "Login succeeds"),
                status="covered",
                evidence=[_evidence("s1", "TC-1", "partial"), _evidence("s1", "TC-2", "full")],
            ),
            AspectCoverage(
                aspect=_aspect("A2", "Lock after 3 failures"),
                status="missing",
                gap_reason="No test fails three times.",
                suggested_test=SuggestedTest(
                    title="Lock after third failure", description="Fail 3x, expect lock <b>"
                ),
            ),
        ],
        "sets_without_evidence": [SetWithoutEvidence(set_key="s2", reason="no_matching_aspect")],
        "reduced_mode": False,
        "incomplete": False,
    }
    values.update(overrides)
    return CoverageResult(**values)


def test_a_contributing_set_lists_its_proofs_and_the_open_aspects():
    assert block_body(_result(), "s1", LanguageOption.ENGLISH) == (
        "Proves for REQ-42: A1 (full).\n"
        "Not covered for REQ-42:\n"
        "- A2 Lock after 3 failures (missing)\n"
        "  Gap: No test fails three times.\n"
        "  Suggested test: Lock after third failure\n"
        "  Test sketch: Fail 3x, expect lock <b>"
    )


def test_a_set_that_could_not_be_evaluated_is_not_told_to_check_its_link():
    result = _result(
        sets_without_evidence=[SetWithoutEvidence(set_key="s2", reason="interpretation_failed")]
    )

    english = block_body(result, "s2", LanguageOption.ENGLISH).splitlines()[0]
    german = block_body(result, "s2", LanguageOption.GERMAN).splitlines()[0]

    assert english == "Could not be evaluated for REQ-42 in this run. Run the check again."
    assert "link" not in english.lower()
    assert "Link" not in german
    assert "erneut" in german


def test_gap_and_sketch_survive_escaping_and_the_block_pattern():
    block = render_set_block(_result(), "s1", LanguageOption.ENGLISH, "2026-10-12 14:03")

    assert "Test sketch: Fail 3x, expect lock &lt;b&gt;" in block
    assert block_pattern(headings(), "REQ-42").fullmatch(block)


def test_a_set_without_evidence_is_told_to_check_its_link():
    body = block_body(_result(), "s2", LanguageOption.GERMAN)

    assert body.splitlines()[0] == (
        "Mit REQ-42 verlinkt, prüft aber keinen ihrer Aspekte (kein passender Aspekt). "
        "Link prüfen oder Anforderung ergänzen."
    )


def test_full_coverage_says_so():
    result = _result(aspects=_result().aspects[:1])

    assert block_body(result, "s1", LanguageOption.ENGLISH).splitlines()[-1] == (
        "All 1 aspects of REQ-42 are covered."
    )


def test_reduced_and_incomplete_runs_are_flagged():
    body = block_body(_result(reduced_mode=True, incomplete=True), "s1", LanguageOption.ENGLISH)

    assert body.splitlines()[-2:] == [
        "Aspects derived from the title only (no requirement description available).",
        "Incomplete: at least one linked test case set could not be evaluated.",
    ]


def test_the_rendered_block_is_found_by_its_own_pattern_in_both_languages():
    for language in LanguageOption:
        block = render_set_block(_result(), "s1", language, "2026-10-12 14:03")

        assert block_pattern(headings(), "REQ-42").fullmatch(block)


def test_the_report_names_status_evidence_gaps_and_sets():
    report = render_report(_result(skipped_comments=["s1"], set_paths={"s1": "/Auth/Login"}))

    assert report.splitlines()[0] == "Coverage of REQ-42: 2 aspects: 1 covered, 0 weak, 1 missing"
    assert "A1 [negative] covered: Login succeeds" in report
    assert "    /Auth/Login / TC-2: full" in report
    assert "    suggested test: Lock after third failure - Fail 3x, expect lock <b>" in report
    assert "Set without evidence: s2 (no_matching_aspect)" in report
    assert "Review comments not written: /Auth/Login" in report
