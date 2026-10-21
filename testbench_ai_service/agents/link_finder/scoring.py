"""The confidence of a link candidate, by fixed rules.

The model names evidence; the code decides how much it is worth. A candidate needs
at least one test that performs and checks an aspect (``full``) to be more than a
hint, and has to touch a good share of the aspects to be likely.
"""

from testbench_ai_service.agents.link_finder.model import CONFIDENCE_ORDER, Confidence
from testbench_ai_service.utils.traceability.models import Aspect, AspectEvidence


def covered_aspect_ids(aspects: list[Aspect], evidence: list[AspectEvidence]) -> list[str]:
    """Aspects with any evidence, in aspect order."""
    touched = {item.aspect_id for item in evidence}
    return [aspect.id for aspect in aspects if aspect.id in touched]


def confidence(
    aspects: list[Aspect],
    evidence: list[AspectEvidence],
    high_confidence_ratio: float,
    reduced_mode: bool,
) -> Confidence | None:
    """The candidate's confidence, or ``None`` if it is dropped.

    In reduced mode the aspects rest on the title alone, so every level drops by
    one and ``low`` is dropped.
    """
    if not evidence:
        return None
    if any(item.strength == "full" for item in evidence):
        share = len(covered_aspect_ids(aspects, evidence)) / len(aspects)
        level: Confidence = "high" if share >= high_confidence_ratio else "medium"
    else:
        level = "low"
    if not reduced_mode:
        return level
    index = CONFIDENCE_ORDER.index(level) + 1
    return CONFIDENCE_ORDER[index] if index < len(CONFIDENCE_ORDER) else None


def rank_key(confidence_level: Confidence, aspects_touched: int, path: str) -> tuple:
    """Sort key: strongest confidence first, then most aspects, then path."""
    return (CONFIDENCE_ORDER.index(confidence_level), -aspects_touched, path)
