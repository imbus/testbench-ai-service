import numpy as np

from testbench_ai_service.agents.test_planner.distance import normalize
from testbench_ai_service.agents.test_planner.model import PlannerRunParams, PlannerTestCase
from testbench_ai_service.agents.test_planner.planner import build_plan
from testbench_ai_service.models.testbench import ActivityStatus

UNIT = normalize(np.array([[1.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]))


def _cases(overrides=None):
    base = []
    for i, set_name in enumerate(["Login", "Login", "Search", "Export"]):
        fields = {
            "unique_id": f"TC-{i}",
            "key": str(i),
            "set_key": f"S-{set_name}",
            "set_name": set_name,
            "path": f"/{set_name}",
            "text": set_name,
            "planned_minutes": 10.0,
        }
        fields.update((overrides or {}).get(i, {}))
        base.append(PlannerTestCase(**fields))
    return base


def test_count_selection_skips_the_duplicate():
    result, notes = build_plan(_cases(), UNIT, PlannerRunParams(mode="count", count=4), None, 0.05)

    # TC-2 and TC-3 tie on the largest mean distance, the lower index wins
    assert [e.unique_id for e in result.selection] == ["TC-2", "TC-0", "TC-3"]
    assert [e.rank for e in result.selection] == [1, 2, 3]
    assert {e.reason for e in result.selection} == {"farthest"}
    assert result.selected == 3
    assert result.total == 4
    assert result.planned_minutes == 30.0
    assert result.cutoff_hints.distance_zero_from == 4
    assert notes == []


def test_duplicates_form_a_cluster():
    result, _ = build_plan(_cases(), UNIT, PlannerRunParams(mode="auto"), None, 0.05)

    assert [c.model_dump() for c in result.redundancy_clusters] == [
        {"tests": ["TC-0", "TC-1"], "sets": ["Login"]}
    ]


def test_mandatory_and_existing_come_first():
    cases = _cases({2: {"tags": frozenset({"must"})}, 3: {"status": ActivityStatus.Planned}})

    result, _ = build_plan(cases, UNIT, PlannerRunParams(mode="count", count=4), "must", 0.05)

    assert [(e.unique_id, e.reason) for e in result.selection] == [
        ("TC-2", "mandatory"),
        ("TC-3", "existing"),
        ("TC-0", "farthest"),
    ]


def test_replan_treats_planned_as_candidates():
    cases = _cases({3: {"status": ActivityStatus.Planned}})
    params = PlannerRunParams(mode="count", count=1, existing="replan")

    result, _ = build_plan(cases, UNIT, params, None, 0.05)

    assert result.selection[0].reason == "farthest"


def test_executed_are_never_selected_but_block_similar_ones():
    cases = _cases({0: {"status": ActivityStatus.Performed}})

    result, _ = build_plan(cases, UNIT, PlannerRunParams(mode="count", count=4), None, 0.05)

    selected = [e.unique_id for e in result.selection]
    assert "TC-0" not in selected
    assert "TC-1" not in selected  # duplicate of the executed TC-0
    assert result.total == 3


def test_notes_are_passed_through():
    params = PlannerRunParams(mode="coverage", coverage_percent=100)

    _, notes = build_plan(_cases(), UNIT, params, None, 0.05)

    assert [n.value for n in notes] == ["no_requirements_fallback"]
