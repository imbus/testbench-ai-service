import numpy as np

from testbench_ai_service.agents.test_planner.clusters import redundancy_clusters
from testbench_ai_service.agents.test_planner.distance import normalize


def test_groups_close_rows_and_drops_singletons():
    unit = normalize(np.array([[1.0, 0.0], [0.0, 1.0], [1.0, 0.01], [0.0, 1.0], [-1.0, 1.0]]))

    assert redundancy_clusters(unit, 0.05) == [[0, 2], [1, 3]]


def test_transitive_chain_is_one_cluster():
    angles = np.radians([0.0, 10.0, 20.0])
    unit = normalize(np.stack([np.cos(angles), np.sin(angles)], axis=1))

    # neighbours are ~0.015 apart, the ends ~0.06: the chain still joins
    assert redundancy_clusters(unit, 0.03) == [[0, 1, 2]]


def test_larger_clusters_first():
    unit = normalize(np.array([[0.0, 1.0], [1.0, 0.0], [1.0, 0.0], [1.0, 0.0], [0.0, 1.0]]))

    assert redundancy_clusters(unit, 0.05) == [[1, 2, 3], [0, 4]]


def test_block_size_does_not_change_the_result():
    rng = np.random.default_rng(2)
    base = rng.normal(size=(5, 16))
    unit = normalize(np.vstack([base, base + rng.normal(scale=0.01, size=(5, 16))]))

    assert redundancy_clusters(unit, 0.05, block_size=3) == redundancy_clusters(unit, 0.05)


def test_identical_vectors_cluster_even_at_threshold_zero_is_empty():
    unit = normalize(np.array([[1.0, 2.0], [1.0, 2.0]]))

    assert redundancy_clusters(unit, 0.05) == [[0, 1]]
    assert redundancy_clusters(unit, 0.0) == []
