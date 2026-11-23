"""Texts the link finder writes: the review block of each candidate and the log report."""

from testbench_ai_service.agents.link_finder.model import LinkCandidate, LinkFinderResult
from testbench_ai_service.models.language import LanguageOption
from testbench_ai_service.utils.i18n import get_translation
from testbench_ai_service.utils.traceability.review_writer import render_block

HEADING_KEY = "link_finder.block.heading"

#: Evidence lines shown per candidate; the log has all of them.
MAX_EVIDENCE_IN_BLOCK = 3


def headings() -> list[str]:
    """The block heading in every language, so a block written in another one is found."""
    return [get_translation(HEADING_KEY, language) for language in LanguageOption]


def _text(key: str, language: LanguageOption, **values) -> str:
    return get_translation(f"link_finder.{key}", language, **values)


def _aspect_list(aspect_ids: list[str], aspects: dict[str, str]) -> str:
    return "; ".join(f"{aspect_id} {aspects[aspect_id]}" for aspect_id in aspect_ids)


def block_body(result: LinkFinderResult, candidate: LinkCandidate, language: LanguageOption) -> str:
    """The plain-text body of one candidate's block.

    Says how likely the set tests the requirement, names the strongest evidence and
    the aspects it touches; a medium candidate also names the aspects it does not
    prove. Other requirements on the set hint at overlapping requirements.
    """
    ref = result.requirement_key
    confidence = _text(f"confidence.{candidate.confidence}", language)
    lines = [_text("block.candidate", language, requirement=ref, confidence=confidence)]

    strongest = sorted(candidate.evidence, key=lambda item: item.strength != "full")
    lines.append(_text("block.evidence", language))
    lines.extend(
        f"- {item.aspect_id}, {item.test_case_key} ({item.strength}): {item.evidence}"
        for item in strongest[:MAX_EVIDENCE_IN_BLOCK]
    )
    lines.append(
        _text(
            "block.touches",
            language,
            aspects=_aspect_list(candidate.covered_aspect_ids, result.aspects),
        )
    )
    if candidate.confidence == "medium":
        proven = {item.aspect_id for item in candidate.evidence if item.strength == "full"}
        unproven = [aspect_id for aspect_id in result.aspects if aspect_id not in proven]
        if unproven:
            lines.append(
                _text("block.not_proven", language, aspects=_aspect_list(unproven, result.aspects))
            )
    if candidate.already_linked_to:
        lines.append(
            _text(
                "block.also_linked",
                language,
                requirements=", ".join(candidate.already_linked_to),
                requirement=ref,
            )
        )
    if result.reduced_mode:
        lines.append(_text("block.reduced_mode", language))
    lines.append(_text("block.decide", language))
    return "\n".join(lines)


def render_candidate_block(
    result: LinkFinderResult, candidate: LinkCandidate, language: LanguageOption, timestamp: str
) -> str:
    return render_block(
        heading=get_translation(HEADING_KEY, language),
        requirement_ref=result.requirement_key,
        body=block_body(result, candidate, language),
        disclaimer=get_translation("shared.run.disclaimer", language),
        timestamp=timestamp,
    )


def render_report(result: LinkFinderResult) -> str:
    """The full result as readable log lines."""
    paths = result.set_paths
    lines = [f"Link candidates for {result.requirement_key}: {result.summary()}"]
    lines.extend(f"{aspect_id} {statement}" for aspect_id, statement in result.aspects.items())
    overlapping = []
    for candidate in result.candidates:
        lines.append(
            f"[{candidate.confidence}] {candidate.path} ({candidate.spec_status}): "
            f"touches {', '.join(candidate.covered_aspect_ids)}"
        )
        lines.extend(
            f"    {item.aspect_id} / {item.test_case_key}: {item.strength} - {item.evidence}"
            for item in candidate.evidence
        )
        if candidate.already_linked_to:
            overlapping.append(
                f"{candidate.path} (linked to {', '.join(candidate.already_linked_to)})"
            )
    if overlapping:
        lines.append("Candidates already linked to other requirements (overlap?):")
        lines.extend(f"    {entry}" for entry in overlapping)
    if result.empty_sets:
        lines.append(
            "Candidates without test cases: "
            + ", ".join(paths.get(key, key) for key in result.empty_sets)
        )
    if result.failed_sets:
        lines.append(
            "Candidates that could not be interpreted: "
            + ", ".join(paths.get(key, key) for key in result.failed_sets)
        )
    if result.skipped_comments:
        lines.append(
            "Review comments not written: "
            + ", ".join(paths.get(key, key) for key in result.skipped_comments)
        )
    if result.reduced_mode:
        lines.append("Reduced mode: aspects derived from the requirement title only")
    if result.incomplete:
        lines.append("Incomplete: at least one prefilter batch or candidate could not be evaluated")
    return "\n".join(lines)
