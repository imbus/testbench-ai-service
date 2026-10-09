"""Sets the selected test cases to planned by importing a JSON execution result."""

import asyncio
import json
import tempfile
import zipfile
from collections.abc import Iterable, Mapping, Sequence
from copy import deepcopy
from dataclasses import asdict
from enum import Enum
from pathlib import Path

from testbench2robotframework.json_reader import TestCaseSet
from testbench2robotframework.model import (
    ActivityStatus,
    ExecutionResultForImport,
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

#: Planned and assigned test cases stay as they are; executed ones keep their results.
_UNTOUCHED = frozenset(status.value for status in EXECUTED_STATUSES | PLANNED_STATUSES)


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
        RuntimeError: If the import job could not be triggered.
    """
    protocol, details = build_planning_import(catalog, unique_ids)
    planned = sum(len(entry.testCases) for entry in protocol)
    if not planned:
        return 0

    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = Path(tmpdir) / "planning.zip"
        write_import_zip(protocol, details, zip_path)
        await _import(conn, context, zip_path)
    return planned


def build_planning_import(
    catalog: Mapping[str, TestCaseSet], unique_ids: Iterable[str]
) -> tuple[list[TestCaseSetExecutionForImport], list[TestCaseSetDetails]]:
    """
    The import protocol and the updated set details that plan ``unique_ids``.

    Marks the test cases as planned in ``catalog`` as well, so the set details
    agree with the protocol. Only sets with at least one change are returned,
    sorted by unique ID.
    """
    wanted = set(unique_ids)
    protocol: list[TestCaseSetExecutionForImport] = []
    details: list[TestCaseSetDetails] = []
    for uid in sorted(catalog):
        test_case_set = catalog[uid]
        set_details = test_case_set.details
        if set_details.exec is None:
            continue
        planned = [
            test_case
            for test_case_uid, test_case in test_case_set.test_cases.items()
            if test_case_uid in wanted
            and test_case.exec is not None
            and test_case.exec.status.value not in _UNTOUCHED
        ]
        if not planned:
            continue

        planned_ids = {test_case.uniqueID for test_case in planned}
        for test_case in planned:
            test_case.exec.status = ActivityStatus.Planned
        for summary in set_details.testCases:
            if summary.uniqueID in planned_ids and summary.exec is not None:
                summary.exec.status = ActivityStatus.Planned

        protocol.append(
            TestCaseSetExecutionForImport(
                testCaseSetKey=set_details.key,
                executionKey=set_details.exec.key,
                durationMillis=0,
                testCases=[
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
                    for test_case in planned
                ],
            )
        )
        details.append(set_details)
    return protocol, details


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

    triggered = await asyncio.to_thread(importer.trigger, connection.active_connection)
    if not triggered:
        raise RuntimeError(
            f"Failed to trigger the import that plans the test cases in cycle '{context.cycle_key}'."
        )
    logger.debug("Triggered the planning import in cycle '%s'", context.cycle_key)
