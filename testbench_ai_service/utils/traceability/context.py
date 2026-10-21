"""The requirement a traceability agent was triggered on, and the tests linked to it.

The requirement's master data comes from the TOV, its description from the RM
service. Linked tests come from the JSON report, which carries requirement links
on test case sets and on single test cases: a set linked as a whole contributes
all its test cases, otherwise only the test cases that link the requirement.
"""

import asyncio
from collections.abc import Iterable, Mapping

from testbench2robotframework.json_reader import TestCaseSet
from testbench_cli_reporter.testbench import Connection as TBConnection

from testbench_ai_service.models.testbench import RequirementAssignment
from testbench_ai_service.utils.html_utils import has_visible_text, visible_text
from testbench_ai_service.utils.rm_service import (
    Requirement,
    RmServiceArgs,
    fetch_requirement_details,
    find_rm_requirement,
)
from testbench_ai_service.utils.testbench import get_requirements, get_test_case_set_catalog
from testbench_ai_service.utils.traceability.models import (
    LinkedSet,
    RequirementContext,
    TestCall,
    TestCase,
    TestCaseSetDetail,
)


class RequirementNotFoundError(LookupError):
    """The trigger names a requirement the TOV does not contain."""


def find_requirement(
    assignments: Iterable[RequirementAssignment], root_key: str | None, root_uid: str | None
) -> RequirementAssignment | None:
    """The triggered requirement: by TestBench key first, else by ID or extended ID."""
    assignments = list(assignments)
    if root_key:
        for assignment in assignments:
            if assignment.key == root_key:
                return assignment
    if root_uid:
        for assignment in assignments:
            if root_uid in (assignment.id, assignment.extendedId, assignment.key):
                return assignment
    return None


def _links(references: Iterable, requirement_key: str) -> bool:
    return any(reference.key == requirement_key for reference in references)


def linked_test_cases(test_case_set: TestCaseSet, requirement_key: str) -> tuple[bool, list]:
    """Whether the set is linked as a whole, and the test cases that count as linked."""
    whole = _links(test_case_set.details.spec.requirements, requirement_key)
    cases = [
        test_case
        for test_case in test_case_set.test_cases.values()
        if whole or _links(test_case.spec.requirements, requirement_key)
    ]
    return whole, cases


def linked_set_keys(catalog: Mapping[str, TestCaseSet], requirement_key: str) -> list[str]:
    """Keys of the sets linked as a whole or through a test case, sorted by path."""
    linked = [
        test_case_set
        for test_case_set in catalog.values()
        if any(linked_test_cases(test_case_set, requirement_key))
    ]
    return [tcs.details.key for tcs in sorted(linked, key=lambda tcs: tcs.details.path)]


def has_linked_test_case(catalog: Mapping[str, TestCaseSet], requirement_key: str) -> bool:
    """Whether at least one test case anywhere counts as linked to the requirement."""
    return any(linked_test_cases(tcs, requirement_key)[1] for tcs in catalog.values())


def _test_case(test_case, set_details) -> TestCase:
    """A report test case as the model sees it; without own sequence it runs the set's."""
    sequence = test_case.testSequence or set_details.testSequence
    return TestCase(
        key=test_case.uniqueID,
        parameters={parameter.name: parameter.value or "" for parameter in test_case.parameters},
        calls=[
            TestCall(
                phase=keyword_call.spec.sequencePhase.value,
                keyword=keyword_call.spec.name,
                check=keyword_call.spec.callType.value == "Check",
                arguments={
                    parameter.name: parameter.value
                    for parameter in keyword_call.spec.callParameters
                    if parameter.value
                },
            )
            for keyword_call in sequence
        ],
    )


def _set_fields(test_case_set: TestCaseSet, cases: Iterable) -> dict:
    details = test_case_set.details
    return {
        "key": details.key,
        "spec_key": details.spec.key,
        "unique_id": details.uniqueID,
        "title": details.name,
        "path": details.path,
        "description": visible_text(details.spec.description or ""),
        "spec_status": details.spec.status.value,
        "test_cases": [_test_case(test_case, details) for test_case in cases],
    }


def _linked_set(test_case_set: TestCaseSet, requirement_key: str) -> LinkedSet:
    whole, cases = linked_test_cases(test_case_set, requirement_key)
    return LinkedSet(**_set_fields(test_case_set, cases), linked_as_whole=whole)


def test_case_set_detail(test_case_set: TestCaseSet) -> TestCaseSetDetail:
    """The set with all its test cases, linked or not."""
    return TestCaseSetDetail(**_set_fields(test_case_set, test_case_set.test_cases.values()))


test_case_set_detail.__test__ = False  # type: ignore[attr-defined]


async def load_requirement(
    conn: TBConnection,
    rm_args: RmServiceArgs,
    project_key: str,
    tov_key: str,
    root_key: str | None,
    root_uid: str | None,
) -> tuple[Requirement, list[RequirementAssignment]]:
    """Load the triggered requirement with its RM description.

    Returns:
        The requirement and all requirement assignments of the TOV.

    Raises:
        RequirementNotFoundError: The TOV has no such requirement.
    """
    assignments = await asyncio.to_thread(get_requirements, conn, project_key, None, tov_key)
    assignment = find_requirement(assignments, root_key, root_uid)
    if assignment is None:
        raise RequirementNotFoundError(
            f"Requirement root_key={root_key!r} root_uid={root_uid!r} is not in TOV '{tov_key}'"
        )
    (extended,) = await fetch_requirement_details(conn, rm_args, tov_key, [assignment])
    return Requirement.from_details(assignment, extended), list(assignments)


async def load_unassigned_requirement(
    conn: TBConnection,
    rm_args: RmServiceArgs,
    tov_key: str,
    root_key: str | None,
    root_uid: str | None,
) -> Requirement | None:
    """Load a requirement the TOV does not assign from the RM service alone.

    Returns:
        The requirement, or ``None`` when no RM service is configured or it does not
        know the requirement.
    """
    ids = [value for value in (root_uid, root_key) if value]
    extended = await find_rm_requirement(conn, rm_args, tov_key, ids)
    if extended is None:
        return None
    # No test references an unassigned requirement, so any key unique to it will do;
    # the TestBench key from the trigger is the right one when it is there.
    return Requirement.from_rm(root_key or extended.key.id, extended)


async def load_requirement_context(
    conn: TBConnection,
    rm_args: RmServiceArgs,
    project_key: str,
    tov_key: str,
    root_key: str | None,
    root_uid: str | None,
    set_keys: list[str],
    catalog: Mapping[str, TestCaseSet] | None = None,
) -> RequirementContext:
    """Load the triggered requirement with its RM description and the given linked sets.

    Args:
        conn: TestBench connection.
        rm_args: Access to the RM service; without a URL the TOV data is used alone.
        project_key: Project of the TOV.
        tov_key: TOV the requirement and the tests belong to.
        root_key: Requirement key from the trigger, if any.
        root_uid: Requirement ID from the trigger, if any.
        set_keys: Keys of the linked sets to load, as the precheck found them.
        catalog: Test case set catalog the precheck already loaded; loaded here if absent.

    Raises:
        RequirementNotFoundError: The TOV has no such requirement.
    """
    requirement, _ = await load_requirement(conn, rm_args, project_key, tov_key, root_key, root_uid)

    if catalog is None:
        catalog = await asyncio.to_thread(
            get_test_case_set_catalog, conn, project_key, tov_key, None, None, None
        )
    wanted = set(set_keys)
    linked_sets = sorted(
        (
            _linked_set(tcs, requirement.key)
            for tcs in catalog.values()
            if tcs.details.key in wanted
        ),
        key=lambda linked_set: linked_set.path,
    )
    return RequirementContext(
        requirement=requirement,
        linked_sets=linked_sets,
        reduced_mode=not has_visible_text(requirement.description or ""),
    )
