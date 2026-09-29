"""Farthest point sampling over the test case embeddings."""

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from testbench_ai_service.agents.test_planner.distance import distances_to, mean_distances


@dataclass(frozen=True)
class Ranking:
    #: Distance of each seed to the ones taken before it (1.0 for the first).
    seed_scores: list[float]
    #: Candidate indices in the order they were picked.
    order: list[int]
    #: Distance of each pick to everything taken before it; non-increasing.
    scores: list[float]


def farthest_point_ranking(
    unit: np.ndarray,
    candidates: Sequence[int],
    seeds: Sequence[int],
    blockers: Sequence[int],
) -> Ranking:
    """
    Rank the candidates so each one is as far as possible from all before it.

    Rows of ``unit`` must be sorted by unique ID: every tie goes to the lowest
    index, which makes the ranking deterministic.

    Args:
        unit: L2-normalised embeddings, one row per test case.
        candidates: Rows that may be picked.
        seeds: Rows taken before any pick (mandatory, already planned), in order.
        blockers: Rows that count as taken but are never reported (executed).

    Returns:
        The scores of the seeds and the complete ranking of the other candidates.
    """
    min_dist = np.full(len(unit), np.inf)

    def take(index: int) -> None:
        np.minimum(min_dist, distances_to(unit, index), out=min_dist)

    for blocker in blockers:
        take(blocker)

    seed_scores: list[float] = []
    for seed in seeds:
        seed_scores.append(_score(min_dist[seed]))
        take(seed)

    remaining = np.zeros(len(unit), dtype=bool)
    remaining[np.asarray(candidates, dtype=np.intp)] = True
    remaining[np.asarray(seeds, dtype=np.intp)] = False
    remaining[np.asarray(blockers, dtype=np.intp)] = False

    order: list[int] = []
    scores: list[float] = []

    def pick(index: int, score: float) -> None:
        order.append(index)
        scores.append(score)
        remaining[index] = False
        take(index)

    if remaining.any() and not seeds and not blockers:
        pick(_argmax_where(mean_distances(unit), remaining), 1.0)

    while remaining.any():
        index = _argmax_where(min_dist, remaining)
        pick(index, _score(min_dist[index]))

    return Ranking(seed_scores=seed_scores, order=order, scores=scores)


def _score(value: float) -> float:
    return 1.0 if np.isinf(value) else float(value)


def _argmax_where(values: np.ndarray, mask: np.ndarray) -> int:
    return int(np.argmax(np.where(mask, values, -np.inf)))
