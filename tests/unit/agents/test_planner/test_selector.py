from itertools import pairwise

import numpy as np

from testbench_ai_service.agents.test_planner.distance import normalize
from testbench_ai_service.agents.test_planner.selector import farthest_point_ranking

# index 0: a, 1: a' (close to a), 2: b, 3: c — indices follow the unique_id order
UNIT = normalize(np.array([[1.0, 0.0, 0.0], [1.0, 0.1, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]))
ALL = [0, 1, 2, 3]


def test_starts_at_largest_mean_distance_then_farthest_with_tie_break():
    ranking = farthest_point_ranking(UNIT, ALL, seeds=[], blockers=[])

    assert ranking.order == [3, 0, 2, 1]
    assert ranking.scores[:3] == [1.0, 1.0, 1.0]
    assert 0.0 < ranking.scores[3] < 0.01
    assert ranking.seed_scores == []


def test_is_deterministic():
    first = farthest_point_ranking(UNIT, ALL, [], [])
    second = farthest_point_ranking(UNIT, ALL, [], [])

    assert first == second


def test_seeds_are_not_ranked_but_shape_the_distances():
    ranking = farthest_point_ranking(UNIT, ALL, seeds=[0], blockers=[])

    assert ranking.order == [2, 3, 1]
    assert ranking.seed_scores == [1.0]


def test_second_seed_scores_its_distance_to_the_first():
    ranking = farthest_point_ranking(UNIT, ALL, seeds=[0, 1], blockers=[])

    assert ranking.seed_scores[0] == 1.0
    assert ranking.seed_scores[1] < 0.01


def test_blockers_shape_the_distances_but_are_never_picked():
    ranking = farthest_point_ranking(UNIT, [1, 2, 3], seeds=[], blockers=[0])

    assert ranking.order == [2, 3, 1]
    assert 0 not in ranking.order


def test_scores_are_non_increasing():
    rng = np.random.default_rng(1)
    unit = normalize(rng.normal(size=(50, 8)))

    scores = farthest_point_ranking(unit, list(range(50)), [], []).scores

    assert all(a >= b for a, b in pairwise(scores))


def test_duplicates_score_zero():
    unit = normalize(np.array([[1.0, 0.0], [1.0, 0.0], [0.0, 1.0]]))

    ranking = farthest_point_ranking(unit, [0, 1, 2], [], [])

    assert ranking.scores[-1] <= 1e-6


def test_first_pick_is_unscored_only_without_seeds_and_blockers():
    assert farthest_point_ranking(UNIT, ALL, [], []).first_unscored is True
    assert farthest_point_ranking(UNIT, ALL, [0], []).first_unscored is False
    assert farthest_point_ranking(UNIT, [1, 2, 3], [], [0]).first_unscored is False
