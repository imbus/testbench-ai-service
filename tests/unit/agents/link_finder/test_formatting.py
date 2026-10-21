"""The text of the review block and of the log report."""

from testbench_ai_service.agents.link_finder.formatting import (
    block_body,
    headings,
    render_candidate_block,
    render_report,
)
from testbench_ai_service.agents.link_finder.model import LinkCandidate, LinkFinderResult
from testbench_ai_service.models.language import LanguageOption
from testbench_ai_service.utils.i18n import load_translations
from testbench_ai_service.utils.traceability.models import AspectEvidence
from testbench_ai_service.utils.traceability.review_writer import block_pattern

load_translations()

EN = LanguageOption.ENGLISH


def _evidence(aspect_id, key, strength, text="e"):
    return AspectEvidence(aspect_id=aspect_id, test_case_key=key, strength=strength, evidence=text)


def _candidate(**overrides):
    values = {
        "set_key": "s1",
        "set_title": "Lock",
        "path": "/Auth/Lock",
        "spec_status": "Released",
        "confidence": "high",
        "covered_aspect_ids": ["A1", "A2"],
        "evidence": [
            _evidence("A2", "TC-2", "partial", "fails twice"),
            _evidence("A1", "TC-1", "full", "expects 'account locked'"),
        ],
        "already_linked_to": [],
    }
    values.update(overrides)
    return LinkCandidate(**values)


def _result(*candidates, **overrides):
    values = {
        "requirement_key": "REQ-42",
        "aspects": {"A1": "Login succeeds", "A2": "Lock after 3 failures", "A3": "Unlock by admin"},
        "candidates": list(candidates),
        "sets_screened": 120,
        "sets_detailed": 3,
        "reduced_mode": False,
        "incomplete": False,
        "set_paths": {"s1": "/Auth/Lock", "s9": "/Empty"},
    }
    values.update(overrides)
    return LinkFinderResult(**values)


def test_a_high_candidate_names_confidence_evidence_and_aspects():
    candidate = _candidate()

    assert block_body(_result(candidate), candidate, EN) == (
        "Probably tests REQ-42, but is not linked to it (confidence: high).\n"
        "Evidence:\n"
        "- A1, TC-1 (full): expects 'account locked'\n"
        "- A2, TC-2 (partial): fails twice\n"
        "Touches: A1 Login succeeds; A2 Lock after 3 failures\n"
        "Check the test steps and link the set if it fits. The agent never sets links."
    )


def test_a_medium_candidate_also_names_what_it_does_not_prove():
    candidate = _candidate(confidence="medium")

    body = block_body(_result(candidate), candidate, EN)

    assert "Not proven here: A2 Lock after 3 failures; A3 Unlock by admin" in body


def test_other_requirements_and_reduced_mode_are_mentioned():
    candidate = _candidate(already_linked_to=["REQ-7"])

    body = block_body(_result(candidate, reduced_mode=True), candidate, EN)

    assert "Already linked to REQ-7: REQ-42 may overlap with them." in body
    assert "confidence lowered by one level" in body


def test_at_most_three_evidence_lines_full_first():
    evidence = [_evidence("A1", f"TC-{n}", "partial") for n in range(4)]
    evidence.append(_evidence("A2", "TC-full", "full"))
    candidate = _candidate(evidence=evidence)

    lines = block_body(_result(candidate), candidate, EN).splitlines()

    shown = [line for line in lines if line.startswith("- ")]
    assert len(shown) == 3
    assert shown[0].startswith("- A2, TC-full (full)")


def test_a_block_in_either_language_is_found_by_the_pattern():
    candidate = _candidate()
    pattern = block_pattern(headings(), "REQ-42")

    assert set(headings()) == {"AI Link Candidate", "KI-Linkvorschlag"}
    for language in LanguageOption:
        assert pattern.search(render_candidate_block(_result(candidate), candidate, language, "t"))


def test_the_coverage_block_is_not_mistaken_for_ours():
    pattern = block_pattern(headings(), "REQ-42")

    assert not pattern.search("<b>AI Coverage REQ-42 - t</b><br/>")


def test_the_german_block():
    candidate = _candidate(confidence="medium")

    body = block_body(_result(candidate), candidate, LanguageOption.GERMAN)

    assert body.startswith(
        "Prüft vermutlich REQ-42, ist aber nicht damit verlinkt (Konfidenz: mittel)."
    )


def test_the_report_lists_candidates_overlaps_and_problems():
    candidate = _candidate(already_linked_to=["REQ-7"])

    report = render_report(
        _result(candidate, empty_sets=["s9"], skipped_comments=["s1"], incomplete=True)
    )

    assert report.splitlines()[0] == (
        "Link candidates for REQ-42: 1 candidates (1 high, 0 medium, 0 low) from 3 of 120 sets"
    )
    assert "[high] /Auth/Lock (Released): touches A1, A2" in report
    assert "    /Auth/Lock (linked to REQ-7)" in report
    assert "Candidates without test cases: /Empty" in report
    assert "Review comments not written: /Auth/Lock" in report
    assert "Incomplete:" in report
