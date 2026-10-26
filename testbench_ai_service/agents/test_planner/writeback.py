"""Sets the selected test cases to planned by importing a JSON execution result."""

import asyncio
import json
import tempfile
import zipfile
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from copy import deepcopy
from dataclasses import asdict
from enum import Enum
from pathlib import Path
from time import monotonic
from typing import NamedTuple

from testbench2robotframework.json_reader import TestCaseSet
from testbench2robotframework.model import (
    ActivityStatus,
    ExecutionResultForImport,
    TestCaseDetails,
    TestCaseExecutionForImport,
    TestCaseSetDetails,
    TestCaseSetExecutionForImport,
)
from testbench_cli_reporter.actions import ImportJSONExecutionResults
from testbench_cli_reporter.config_model import ImportJsonParameters
from testbench_cli_reporter.testbench import Connection as TBConnection
from testbench_cli_reporter.testbench import ConnectionLog
from testbench_cli_reporter.util import TYPICAL_JSON_IMPORT_CONFIG

from testbench_ai_service.agents.test_planner.model import EXECUTED_STATUSES, PLANNED_STATUSES
from testbench_ai_service.log import logger
from testbench_ai_service.models.agent import ExecutionContext

#: How long TestBench may take to run the planning import, and how often to ask.
IMPORT_TIMEOUT_SEC = 300
IMPORT_POLL_INTERVAL_SEC = 1.0

_PLANNED = frozenset(status.value for status in PLANNED_STATUSES)
_EXECUTED = frozenset(status.value for status in EXECUTED_STATUSES)


class PlanningImport(NamedTuple):
    protocol: list[TestCaseSetExecutionForImport]
    details: list[TestCaseSetDetails]
    #: Number of selected test cases left alone, by reason.
    skipped: Counter[str]


async def plan_test_cases(
    conn: TBConnection,
    context: ExecutionContext,
    catalog: Mapping[str, TestCaseSet],
    unique_ids: Iterable[str],
) -> int:
    """
    Set the given test cases of the cycle to ``Planned``.

    Test cases that are planned, assigned or executed already are left alone.

    Returns:
        The number of test cases whose status was changed.

    Raises:
        RuntimeError: If the import job could not be triggered, or TestBench
            reports that it failed.
        TimeoutError: If TestBench has not finished the import in time.
    """
    planning = build_planning_import(catalog, unique_ids)
    if planning.skipped:
        logger.info(
            "Test planner skipped %d selected test cases | %s | cycle='%s'",
            planning.skipped.total(),
            ", ".join(f"{reason}={count}" for reason, count in sorted(planning.skipped.items())),
            context.cycle_key,
        )
    planned = sum(len(entry.testCases) for entry in planning.protocol)
    if not planned:
        return 0

    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = Path(tmpdir) / "planning.zip"
        write_import_zip(planning.protocol, planning.details, zip_path)
        await _import(conn, context, zip_path)
    return planned


def build_planning_import(
    catalog: Mapping[str, TestCaseSet], unique_ids: Iterable[str]
) -> PlanningImport:
    """
    The import protocol and the updated set details that plan ``unique_ids``.

    Marks the test cases as planned in ``catalog`` as well, so the set details
    agree with the protocol. Only sets with at least one change are returned,
    sorted by unique ID, together with the reasons for every test case left alone.
    """
    wanted = set(unique_ids)
    protocol: list[TestCaseSetExecutionForImport] = []
    details: list[TestCaseSetDetails] = []
    skipped: Counter[str] = Counter()
    for uid in sorted(catalog):
        test_case_set = catalog[uid]
        set_details = test_case_set.details
        selected = [
            test_case
            for test_case_uid, test_case in test_case_set.test_cases.items()
            if test_case_uid in wanted
        ]
        if not selected:
            continue
        wanted.difference_update(test_case.uniqueID for test_case in selected)
        if set_details.exec is None:
            skipped["set without execution"] += len(selected)
            continue
        planned = []
        for test_case in selected:
            if reason := _skip_reason(test_case):
                skipped[reason] += 1
            else:
                planned.append(test_case)
        if planned:
            protocol.append(_mark_planned(set_details, planned))
            details.append(set_details)
    if wanted:
        skipped["not in report"] = len(wanted)
    return PlanningImport(protocol, details, skipped)


def _skip_reason(test_case: TestCaseDetails) -> str | None:
    """Why ``test_case`` cannot be set to planned, or ``None`` if it can."""
    if test_case.exec is None:
        return "no execution"
    if test_case.exec.status.value in _PLANNED:
        return "already planned"
    if test_case.exec.status.value in _EXECUTED:
        return "executed"
    return None


def _mark_planned(
    set_details: TestCaseSetDetails, planned: Sequence[TestCaseDetails]
) -> TestCaseSetExecutionForImport:
    """Mark ``planned`` as planned in ``set_details`` and build their protocol entry."""
    assert set_details.exec is not None
    planned_ids = {test_case.uniqueID for test_case in planned}
    for summary in set_details.testCases:
        if summary.uniqueID in planned_ids and summary.exec is not None:
            summary.exec.status = ActivityStatus.Planned
    entries = []
    for test_case in planned:
        assert test_case.exec is not None
        test_case.exec.status = ActivityStatus.Planned
        entries.append(
            TestCaseExecutionForImport(
                uniqueID=test_case.uniqueID,
                testCaseExecutionKey=test_case.exec.key,
                durationMillis=0,
                result=ExecutionResultForImport(
                    status=ActivityStatus.Planned,
                    execStatus=test_case.exec.execStatus,
                    verdict=test_case.exec.verdict,
                ),
            )
        )
    return TestCaseSetExecutionForImport(
        testCaseSetKey=set_details.key,
        executionKey=set_details.exec.key,
        durationMillis=0,
        testCases=entries,
    )


def write_import_zip(
    protocol: Sequence[TestCaseSetExecutionForImport],
    details: Sequence[TestCaseSetDetails],
    path: Path,
) -> None:
    """Write ``protocol.json`` and one ``<uniqueID>.json`` per test case set into a ZIP."""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zipf:
        zipf.writestr("protocol.json", _dumps([asdict(entry) for entry in protocol]))
        for set_details in details:
            zipf.writestr(f"{set_details.uniqueID}.json", _dumps(asdict(set_details)))


def _dumps(content: object) -> str:
    return json.dumps(content, indent=2, default=_enum_value)


def _enum_value(obj: object) -> object:
    if isinstance(obj, Enum):
        return obj.value
    raise TypeError(f"Type {type(obj)} not serializable")


async def _import(conn: TBConnection, context: ExecutionContext, path: Path) -> None:
    connection = ConnectionLog()
    connection.add_connection(conn)

    import_config = deepcopy(TYPICAL_JSON_IMPORT_CONFIG)
    # A planned test case is not executed; the typical config would drop it.
    import_config.ignoreNonExecutedTestCases = False
    parameters = ImportJsonParameters(
        inputPath=str(path),
        projectKey=context.project_key,
        cycleKey=context.cycle_key,
        importConfig=import_config,
    )
    importer = ImportJSONExecutionResults(parameters=parameters)

    active = connection.active_connection
    triggered = await asyncio.to_thread(importer.trigger, active)
    if not triggered:
        raise RuntimeError(
            f"Failed to trigger the import that plans the test cases in cycle '{context.cycle_key}'."
        )
    logger.debug("Triggered the planning import in cycle '%s'", context.cycle_key)

    # Not importer.wait(): it polls without a time limit and prints a progress bar.
    deadline = monotonic() + IMPORT_TIMEOUT_SEC
    while True:
        try:
            finished = await asyncio.to_thread(importer.poll, active)
        except AssertionError as e:
            # How testbench_cli_reporter reports a job that TestBench ended with a failure.
            raise RuntimeError(
                f"TestBench could not plan the test cases in cycle '{context.cycle_key}': {e}"
            ) from e
        if finished:
            return
        if monotonic() >= deadline:
            raise TimeoutError(
                f"The planning import in cycle '{context.cycle_key}' did not finish "
                f"within {IMPORT_TIMEOUT_SEC} seconds."
            )
        await asyncio.sleep(IMPORT_POLL_INTERVAL_SEC)
