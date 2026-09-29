"""Reads the test cases of a cycle from the TestBench JSON report."""

from collections.abc import Iterable, Mapping

from testbench2robotframework.json_reader import TestCaseSet
from testbench_cli_reporter.testbench import Connection as TBConnection

from testbench_ai_service.agents.test_planner.model import PlannerTestCase
from testbench_ai_service.agents.test_planner.text import build_embedding_text
from testbench_ai_service.models.agent import ExecutionContext
from testbench_ai_service.models.testbench import ActivityStatus
from testbench_ai_service.utils.html_utils import extract_text_from_html_body
from testbench_ai_service.utils.testbench import get_test_case_set_catalog

#: ``plannedDuration`` is in milliseconds, like ``actualDuration``.
MILLISECONDS_PER_MINUTE = 60_000


def collect_test_cases(conn: TBConnection, context: ExecutionContext) -> list[PlannerTestCase]:
    """Load every test case in the scope of ``context``, sorted by unique ID."""
    assert context.tov_key is not None
    catalog = get_test_case_set_catalog(
        conn,
        context.project_key,
        context.tov_key,
        context.cycle_key,
        context.root_uid,
        context.filtering,
    )
    return test_cases_from_catalog(catalog)


def test_cases_from_catalog(catalog: Mapping[str, TestCaseSet]) -> list[PlannerTestCase]:
    """Turn a test case set catalog into planner test cases, sorted by unique ID."""
    test_cases: list[PlannerTestCase] = []
    for test_case_set in catalog.values():
        details = test_case_set.details
        description = extract_text_from_html_body(details.spec.description or "")
        set_tags = _names(details.spec.tags)
        set_requirements = {requirement.key for requirement in details.spec.requirements}
        for test_case in test_case_set.test_cases.values():
            execution = test_case.exec
            sequence = test_case.testSequence or details.testSequence
            test_cases.append(
                PlannerTestCase(
                    unique_id=test_case.uniqueID,
                    key=test_case.spec.key,
                    set_key=details.key,
                    set_name=details.name,
                    path=details.path,
                    text=build_embedding_text(
                        details.name,
                        description,
                        [_format_step(call) for call in sequence],
                        {param.name: param.value or "" for param in test_case.parameters},
                    ),
                    planned_minutes=(
                        execution.plannedDuration / MILLISECONDS_PER_MINUTE if execution else 0.0
                    ),
                    tags=frozenset(
                        set_tags
                        | _names(test_case.spec.tags)
                        | (_names(execution.tags) if execution else set())
                    ),
                    requirement_keys=frozenset(
                        set_requirements | {req.key for req in test_case.spec.requirements}
                    ),
                    status=(
                        ActivityStatus(execution.status.value)
                        if execution
                        else ActivityStatus.NotPlanned
                    ),
                )
            )
    return sorted(test_cases, key=lambda test_case: test_case.unique_id)


# pytest would otherwise collect the function above because of its name
test_cases_from_catalog.__test__ = False  # type: ignore[attr-defined]


def _names(tags: Iterable) -> set[str]:
    return {tag.name for tag in tags}


def _format_step(call) -> str:
    spec = call.spec
    arguments = ", ".join(
        f"{param.name}={param.value}" for param in spec.callParameters if param.value
    )
    return f"{spec.sequencePhase.value}: {spec.name}({arguments})"
