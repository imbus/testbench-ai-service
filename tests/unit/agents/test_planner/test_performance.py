import time

import numpy as np
import pytest

from testbench_ai_service.agents.test_planner.clusters import redundancy_clusters
from testbench_ai_service.agents.test_planner.distance import normalize
from testbench_ai_service.agents.test_planner.selector import farthest_point_ranking


@pytest.mark.slow
def test_6500_test_cases_within_30_seconds():
    unit = normalize(np.random.default_rng(0).normal(size=(6500, 1536)))
    start = time.perf_counter()

    ranking = farthest_point_ranking(unit, list(range(6500)), [], [])
    redundancy_clusters(unit, 0.05)

    assert len(ranking.order) == 6500
    assert time.perf_counter() - start < 30
