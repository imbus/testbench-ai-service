"""Texts the coverage checker writes: the review block of each set and the log report."""

from testbench_ai_service.agents.coverage_checker.model import CoverageResult
from testbench_ai_service.models.language import LanguageOption
from testbench_ai_service.utils.i18n import get_translation
from testbench_ai_service.utils.traceability.review_writer import render_block

HEADING_KEY = "coverage_checker.block.heading"


def headings() -> list[str]:
    """The block heading in every language, so a block written in another one is found."""
    return [get_translation(HEADING_KEY, language) for language in LanguageOption]


def _text(key: str, language: LanguageOption, **values) -> str:
    return get_translation(f"coverage_checker.{key}", language, **values)


def block_body(result: CoverageResult, set_key: str, language: LanguageOption) -> str:
    """The plain-text body of one set's block.

    A set proving something lists its own evidence per aspect (the stronger, if
    several test cases prove it); one proving nothing is told to check its link.
    Every block lists the requirement's open aspects, since the requirement itself
    cannot be written to.
    """
    ref = result.requirement_key
    without = {entry.set_key: entry.reason for entry in result.sets_without_evidence}
    lines: list[str] = []
    if set_key in without:
        reason = _text(f"reason.{without[set_key]}", language)
        lines.append(_text("block.proves_nothing", language, requirement=ref, reason=reason))
    else:
        own: dict[str, str] = {}
        for coverage in result.aspects:
            for item in coverage.evidence:
                if item.set_key == set_key and own.get(coverage.aspect.id) != "full":
                    own[coverage.aspect.id] = item.strength
        proofs = ", ".join(f"{aspect_id} ({strength})" for aspect_id, strength in own.items())
        lines.append(_text("block.proves", language, requirement=ref, aspects=proofs))

    open_aspects = [coverage for coverage in result.aspects if coverage.status != "covered"]
    if open_aspects:
        lines.append(_text("block.open", language, requirement=ref))
        for coverage in open_aspects:
            status = _text(f"status.{coverage.status}", language)
            item = _text(
                "block.open_item",
                language,
                id=coverage.aspect.id,
                statement=coverage.aspect.statement,
                status=status,
            )
            lines.append(f"- {item}")
            if coverage.suggested_test is not None:
                suggestion = _text(
                    "block.suggestion", language, title=coverage.suggested_test.title
                )
                lines.append(f"  {suggestion}")
    else:
        lines.append(
            _text("block.all_covered", language, count=len(result.aspects), requirement=ref)
        )
    if result.reduced_mode:
        lines.append(_text("block.reduced_mode", language))
    if result.incomplete:
        lines.append(_text("block.incomplete", language))
    return "\n".join(lines)


def render_set_block(
    result: CoverageResult, set_key: str, language: LanguageOption, timestamp: str
) -> str:
    return render_block(
        heading=get_translation(HEADING_KEY, language),
        requirement_ref=result.requirement_key,
        body=block_body(result, set_key, language),
        disclaimer=get_translation("shared.run.disclaimer", language),
        timestamp=timestamp,
    )


def render_report(result: CoverageResult) -> str:
    """The full matrix as readable log lines."""
    paths = result.set_paths
    lines = [f"Coverage of {result.requirement_key}: {result.summary()}"]
    for coverage in result.aspects:
        aspect = coverage.aspect
        status = coverage.status
        if coverage.weak_reason:
            status += f" ({coverage.weak_reason})"
        lines.append(f"{aspect.id} [{aspect.kind}] {status}: {aspect.statement}")
        lines.extend(
            f"    {paths.get(item.set_key, item.set_key)} / {item.test_case_key}: {item.strength}"
            for item in coverage.evidence
        )
        if coverage.gap_reason:
            lines.append(f"    gap: {coverage.gap_reason}")
        if coverage.suggested_test is not None:
            suggested = coverage.suggested_test
            lines.append(f"    suggested test: {suggested.title} - {suggested.description}")
    lines.extend(
        f"Set without evidence: {paths.get(entry.set_key, entry.set_key)} ({entry.reason})"
        for entry in result.sets_without_evidence
    )
    if result.skipped_comments:
        skipped = ", ".join(paths.get(key, key) for key in result.skipped_comments)
        lines.append(f"Review comments not written: {skipped}")
    if result.reduced_mode:
        lines.append("Reduced mode: aspects derived from the requirement title only")
    if result.incomplete:
        lines.append("Incomplete: at least one linked set could not be interpreted")
    return "\n".join(lines)
