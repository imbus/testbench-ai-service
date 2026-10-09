from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from testbench_ai_service.agents.test_planner.collector import (
    load_catalog,
    test_cases_from_catalog,
)
from testbench_ai_service.models.testbench import ActivityStatus


def _tag(name):
    return SimpleNamespace(name=name)


def _req(key):
    return SimpleNamespace(key=key)


def _call(name, phase="TestStep", **params):
    return SimpleNamespace(
        spec=SimpleNamespace(
            name=name,
            sequencePhase=SimpleNamespace(value=phase),
            callParameters=[SimpleNamespace(name=k, value=v) for k, v in params.items()],
        )
    )


def _test_case(
    uid,
    key,
    *,
    status="NotPlanned",
    duration=0,
    params=None,
    sequence=None,
    tags=(),
    exec_tags=(),
    reqs=(),
    with_exec=True,
):
    execution = (
        SimpleNamespace(
            status=SimpleNamespace(value=status),
            plannedDuration=duration,
            tags=[_tag(t) for t in exec_tags],
        )
        if with_exec
        else None
    )
    return SimpleNamespace(
        uniqueID=uid,
        spec=SimpleNamespace(
            key=key, tags=[_tag(t) for t in tags], requirements=[_req(r) for r in reqs]
        ),
        testSequence=sequence or [],
        parameters=[SimpleNamespace(name=k, value=v) for k, v in (params or {}).items()],
        exec=execution,
    )


def _set(
    uid,
    name,
    test_cases,
    *,
    description="<html><body><p>Desc</p></body></html>",
    sequence=None,
    tags=(),
    reqs=(),
):
    details = SimpleNamespace(
        key=f"K-{uid}",
        uniqueID=uid,
        name=name,
        path=f"/Root/{name}",
        spec=SimpleNamespace(
            description=description,
            tags=[_tag(t) for t in tags],
            requirements=[_req(r) for r in reqs],
        ),
        testSequence=sequence or [],
    )
    return SimpleNamespace(details=details, test_cases={tc.uniqueID: tc for tc in test_cases})


def test_one_planner_case_per_test_case_sorted_by_uid():
    catalog = {
        "S1": _set("S1", "Login", [_test_case("TC-2", "2"), _test_case("TC-1", "1")]),
    }

    cases = test_cases_from_catalog(catalog)

    assert [c.unique_id for c in cases] == ["TC-1", "TC-2"]
    assert cases[0].set_key == "K-S1"
    assert cases[0].set_name == "Login"
    assert cases[0].path == "/Root/Login"


def test_text_uses_description_sequence_and_own_parameters():
    tc = _test_case("TC-1", "1", params={"user": "bob"})
    catalog = {"S1": _set("S1", "Login", [tc], sequence=[_call("Open", url="x", empty="")])}

    [case] = test_cases_from_catalog(catalog)

    assert case.text == "Login\nDesc\nTestStep: Open(url=x)\nuser=bob"


def test_test_case_sequence_wins_over_set_sequence():
    tc = _test_case("TC-1", "1", sequence=[_call("Own")])
    catalog = {"S1": _set("S1", "S", [tc], sequence=[_call("SetLevel")])}

    [case] = test_cases_from_catalog(catalog)

    assert "Own()" in case.text
    assert "SetLevel" not in case.text


def test_duration_status_tags_and_requirements():
    tc = _test_case(
        "TC-1", "1", status="Planned", duration=90_000, tags=("a",), exec_tags=("b",), reqs=("R2",)
    )
    catalog = {"S1": _set("S1", "S", [tc], tags=("mandatory",), reqs=("R1",))}

    [case] = test_cases_from_catalog(catalog)

    assert case.planned_minutes == 1.5
    assert case.status == ActivityStatus.Planned
    assert case.tags == frozenset({"a", "b", "mandatory"})
    assert case.requirement_keys == frozenset({"R1", "R2"})


def test_test_cases_without_execution_in_the_cycle_are_left_out():
    catalog = {
        "S1": _set("S1", "S", [_test_case("TC-1", "1", with_exec=False), _test_case("TC-2", "2")])
    }

    assert [case.unique_id for case in test_cases_from_catalog(catalog)] == ["TC-2"]


def test_collect_passes_the_scope_to_the_report():
    context = SimpleNamespace(
        project_key="P", tov_key="T", cycle_key="C", root_uid="R", filtering=None
    )
    conn = MagicMock()
    with patch(
        "testbench_ai_service.agents.test_planner.collector.get_test_case_set_catalog",
        return_value={},
    ) as catalog:
        assert load_catalog(conn, context) == {}

    # only test cases executable in the cycle can be planned
    catalog.assert_called_once_with(conn, "P", "T", "C", "R", None, suppress_not_executable=True)
