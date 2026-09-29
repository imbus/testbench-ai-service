"""Where the ranking ends: the four cut-off modes and the hints for the user."""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

import numpy as np

from testbench_ai_service.agents.test_planner.model import (
    CutoffHints,
    CutoffMode,
    PlannerRunParams,
    SelectionReason,
)

#: Picks at or below this distance are indistinguishable duplicates.
EPS_ZERO = 1e-6
#: Below this many points a curve has no knee.
MIN_KNEE_POINTS = 3


@dataclass(frozen=True)
class RankedEntry:
    index: int
    reason: SelectionReason
    min_distance: float
    minutes: float
    requirements: frozenset[str]


class CutoffNote(str, Enum):
    SEEDS_EXCEED_COUNT = "seeds_exceed_count"
    SEEDS_EXCEED_BUDGET = "seeds_exceed_budget"
    NO_REQUIREMENTS_FALLBACK = "no_requirements_fallback"


@dataclass(frozen=True)
class CutoffOutcome:
    #: Number of leading entries that are selected.
    length: int
    notes: list[CutoffNote]


def knee_index(scores: Sequence[float]) -> int:
    """
    Index of the knee of a non-increasing score curve (Kneedle).

    Both axes are scaled to ``[0, 1]``; the knee is the point furthest below
    the line from the first to the last point, the earliest on a tie. A curve
    that is too short or has no point below that line has its last point as knee.
    """
    count = len(scores)
    if count < MIN_KNEE_POINTS:
        return count - 1
    values = np.asarray(scores, dtype=np.float64)
    low, high = values.min(), values.max()
    if high - low <= 0:
        return count - 1
    scaled = (values - low) / (high - low)
    gap = (1.0 - np.linspace(0.0, 1.0, count)) - scaled
    index = int(np.argmax(gap))
    return index if gap[index] > 0 else count - 1


def duplicate_limit(entries: Sequence[RankedEntry], seed_count: int) -> int:
    """Number of entries before the first pick that duplicates a selected one."""
    for position in range(seed_count, len(entries)):
        if entries[position].min_distance <= EPS_ZERO:
            return position
    return len(entries)


def apply_cutoff(
    entries: Sequence[RankedEntry],
    seed_count: int,
    params: PlannerRunParams,
    all_requirements: frozenset[str],
    skip_first: bool = False,
) -> CutoffOutcome:
    """
    Decide how many leading entries are selected.

    Args:
        entries: Seeds first (``seed_count`` of them), then the picks in rank order.
        seed_count: Number of seeds; they are selected in every mode.
        params: The run parameters with the cut-off mode and its value.
        all_requirements: Requirement keys of every selectable test case.
        skip_first: The first pick has a placeholder score (nothing before it)
            and is left out of the knee computation.

    Returns:
        The number of selected entries and notes about deviations.
    """
    limit = duplicate_limit(entries, seed_count)
    notes: list[CutoffNote] = []
    mode = params.mode

    if mode == CutoffMode.COVERAGE and not all_requirements:
        notes.append(CutoffNote.NO_REQUIREMENTS_FALLBACK)
        mode = CutoffMode.AUTO

    if mode == CutoffMode.COUNT:
        assert params.count is not None
        if seed_count > params.count:
            notes.append(CutoffNote.SEEDS_EXCEED_COUNT)
        length = max(seed_count, min(params.count, limit))
    elif mode == CutoffMode.BUDGET:
        assert params.budget_minutes is not None
        length = _budget_length(entries, seed_count, limit, params.budget_minutes, notes)
    elif mode == CutoffMode.COVERAGE:
        assert params.coverage_percent is not None
        target = params.coverage_percent / 100 * len(all_requirements)
        length = _coverage_length(entries, seed_count, limit, all_requirements, target)
    else:
        length = _knee_length(entries, seed_count, limit, skip_first)

    return CutoffOutcome(length=length, notes=notes)


def compute_hints(
    entries: Sequence[RankedEntry],
    seed_count: int,
    all_requirements: frozenset[str],
    skip_first: bool = False,
) -> CutoffHints:
    """The 1-based ranks where the knee, full coverage and duplicates start.

    ``skip_first`` as in :func:`apply_cutoff`.
    """
    limit = duplicate_limit(entries, seed_count)
    has_picks = limit > seed_count
    full_coverage = None
    if all_requirements:
        covered: set[str] = set()
        for rank, entry in enumerate(entries, start=1):
            covered |= entry.requirements & all_requirements
            if len(covered) == len(all_requirements):
                full_coverage = rank
                break
    return CutoffHints(
        knee=_knee_length(entries, seed_count, limit, skip_first) if has_picks else None,
        full_requirement_coverage=full_coverage,
        distance_zero_from=limit + 1 if limit < len(entries) else None,
    )


def _budget_length(
    entries: Sequence[RankedEntry],
    seed_count: int,
    limit: int,
    budget: float,
    notes: list[CutoffNote],
) -> int:
    total = sum(entry.minutes for entry in entries[:seed_count])
    if total > budget:
        notes.append(CutoffNote.SEEDS_EXCEED_BUDGET)
    length = seed_count
    for entry in entries[seed_count:limit]:
        if total + entry.minutes > budget:
            break
        total += entry.minutes
        length += 1
    return length


def _coverage_length(
    entries: Sequence[RankedEntry],
    seed_count: int,
    limit: int,
    all_requirements: frozenset[str],
    target: float,
) -> int:
    covered: set[str] = set()
    for entry in entries[:seed_count]:
        covered |= entry.requirements & all_requirements
    length = seed_count
    for entry in entries[seed_count:limit]:
        if len(covered) >= target:
            break
        covered |= entry.requirements & all_requirements
        length += 1
    return length


def _knee_length(
    entries: Sequence[RankedEntry], seed_count: int, limit: int, skip_first: bool = False
) -> int:
    scores = [entry.min_distance for entry in entries[seed_count:limit]]
    if not scores:
        return seed_count
    if skip_first:
        # The placeholder 1.0 would dominate the normalisation of the real,
        # usually much smaller distances; the first pick is always taken.
        if len(scores) == 1:
            return seed_count + 1
        return seed_count + 1 + knee_index(scores[1:]) + 1
    return seed_count + knee_index(scores) + 1
