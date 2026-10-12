import numpy as np
import pytest

from testbench_ai_service.agents.test_planner.distance import (
    close_pairs,
    distances_to,
    mean_distances,
    normalize,
)


def test_normalize_gives_unit_rows_and_keeps_zero_rows():
    unit = normalize(np.array([[3.0, 4.0], [0.0, 0.0]]))

    assert unit.dtype == np.float32
    assert np.allclose(unit[0], [0.6, 0.8])
    assert np.allclose(unit[1], [0.0, 0.0])


def test_distances_to_orthogonal_opposite_and_self():
    unit = normalize(np.array([[1.0, 0.0], [0.0, 1.0], [-1.0, 0.0]]))

    assert np.allclose(distances_to(unit, 0), [0.0, 1.0, 1.0])


def test_identical_vectors_have_zero_distance():
    vector = np.random.default_rng(0).normal(size=1536)
    unit = normalize(np.stack([vector, vector]))

    distances = distances_to(unit, 0)

    assert distances.min() >= 0.0
    assert distances[1] <= 1e-6


def test_mean_distances():
    unit = normalize(np.array([[1.0, 0.0], [1.0, 0.0], [0.0, 1.0]]))

    assert np.allclose(mean_distances(unit), [1 / 3, 1 / 3, 2 / 3])


@pytest.mark.parametrize("block_size", [1, 2, 1024])
def test_close_pairs_across_block_boundaries(block_size):
    unit = normalize(np.array([[1.0, 0.0], [0.0, 1.0], [1.0, 0.01], [0.0, 1.0]]))

    assert sorted(close_pairs(unit, 0.05, block_size)) == [(0, 2), (1, 3)]


def test_close_pairs_threshold_zero_finds_nothing():
    unit = normalize(np.array([[1.0, 0.0], [1.0, 0.0]]))

    assert close_pairs(unit, 0.0) == []
