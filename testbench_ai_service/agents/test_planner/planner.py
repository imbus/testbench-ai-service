"""Puts selector, cut-off and clusters together into one plan."""

from collections.abc import Sequence

import numpy as np

from testbench_ai_service.agents.test_planner.clusters import redundancy_clusters
from testbench_ai_service.agents.test_planner.cutoff import (
    CutoffNote,
    RankedEntry,
    apply_cutoff,
    compute_hints,
)
from testbench_ai_service.agents.test_planner.model import (
    ExistingMode,
    PlannerResult,
    PlannerRunParams,
    PlannerTestCase,
    RedundancyCluster,
    SelectionEntry,
)
from testbench_ai_service.agents.test_planner.selector import farthest_point_ranking


def build_plan(
    test_cases: Sequence[PlannerTestCase],
    unit: np.ndarray,
    params: PlannerRunParams,
    mandatory_tag: str | None,
    cluster_threshold: float,
) -> tuple[PlannerResult, list[CutoffNote]]:
    """
    Select the test cases to plan.

    Args:
        test_cases: All test cases in scope, sorted by unique ID.
        unit: L2-normalised embeddings; row ``i`` belongs to ``test_cases[i]``.
        params: The run parameters.
        mandatory_tag: Tag of the test cases that are always selected.
        cluster_threshold: Distance below which test cases count as redundant.

    Returns:
        The result without warnings, and the notes of the cut-off.
    """
    executed = [i for i, case in enumerate(test_cases) if case.executed]
    candidates = [i for i, case in enumerate(test_cases) if not case.executed]
    mandatory = [
        i for i in candidates if mandatory_tag is not None and mandatory_tag in test_cases[i].tags
    ]
    mandatory_set = set(mandatory)
    existing = [
        i
        for i in candidates
        if params.existing == ExistingMode.KEEP and test_cases[i].planned and i not in mandatory_set
    ]
    seeds = mandatory + existing

    ranking = farthest_point_ranking(unit, candidates, seeds, executed)

    def entry(index: int, reason, score: float) -> RankedEntry:
        case = test_cases[index]
        return RankedEntry(index, reason, score, case.planned_minutes, case.requirement_keys)

    reasons = ["mandatory"] * len(mandatory) + ["existing"] * len(existing)
    entries = [
        entry(index, reason, score)
        for index, reason, score in zip(seeds, reasons, ranking.seed_scores, strict=True)
    ] + [
        entry(index, "farthest", score)
        for index, score in zip(ranking.order, ranking.scores, strict=True)
    ]

    all_requirements = frozenset().union(*(test_cases[i].requirement_keys for i in candidates))
    outcome = apply_cutoff(
        entries, len(seeds), params, all_requirements, skip_first=ranking.first_unscored
    )
    chosen = entries[: outcome.length]

    selection = [
        SelectionEntry(
            rank=rank,
            unique_id=test_cases[chosen_entry.index].unique_id,
            key=test_cases[chosen_entry.index].key,
            path=test_cases[chosen_entry.index].path,
            min_distance=round(chosen_entry.min_distance, 4),
            reason=chosen_entry.reason,
        )
        for rank, chosen_entry in enumerate(chosen, start=1)
    ]
    clusters = [
        RedundancyCluster(
            tests=[test_cases[i].unique_id for i in group],
            sets=sorted({test_cases[i].set_name for i in group}),
        )
        for group in redundancy_clusters(unit, cluster_threshold)
    ]
    result = PlannerResult(
        selected=len(chosen),
        total=len(candidates),
        planned_minutes=round(sum(chosen_entry.minutes for chosen_entry in chosen), 1),
        mode=params.mode,
        cutoff_hints=compute_hints(
            entries, len(seeds), all_requirements, skip_first=ranking.first_unscored
        ),
        selection=selection,
        redundancy_clusters=clusters,
    )
    return result, outcome.notes
