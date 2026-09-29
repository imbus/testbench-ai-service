"""Groups of test cases that are nearly the same and add little coverage."""

import numpy as np

from testbench_ai_service.agents.test_planner.distance import close_pairs


def redundancy_clusters(
    unit: np.ndarray, threshold: float, block_size: int = 1024
) -> list[list[int]]:
    """
    Connected groups of rows whose distance is below ``threshold``.

    Two rows land in one group when a chain of close pairs links them.

    Returns:
        Groups of at least two rows, each sorted, larger groups first and
        equal sizes by their lowest row.
    """
    parent = list(range(len(unit)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for first, second in close_pairs(unit, threshold, block_size):
        root_first, root_second = find(first), find(second)
        if root_first != root_second:
            parent[max(root_first, root_second)] = min(root_first, root_second)

    groups: dict[int, list[int]] = {}
    for index in range(len(unit)):
        groups.setdefault(find(index), []).append(index)

    clusters = [group for group in groups.values() if len(group) >= 2]
    clusters.sort(key=lambda group: (-len(group), group[0]))
    return clusters
