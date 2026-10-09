import json
import logging
import zipfile
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from testbench2robotframework.model import ActivityStatus, ExecStatus, VerdictStatus

from testbench_ai_service.agents.test_planner.writeback import (
    build_planning_import,
    plan_test_cases,
    write_import_zip,
)

_MODULE = "testbench_ai_service.agents.test_planner.writeback"


def _execution(key, status, exec_status=ExecStatus.NotBlocked, verdict=VerdictStatus.Undefined):
    return SimpleNamespace(key=key, status=status, execStatus=exec_status, verdict=verdict)


def _set(uid, test_cases, *, with_exec=True):
    """A catalog entry; ``test_cases`` maps unique IDs to their status or ``None``."""
    details_cases = {
        tc_uid: SimpleNamespace(
            uniqueID=tc_uid, exec=_execution(f"E-{tc_uid}", status) if status else None
        )
        for tc_uid, status in test_cases.items()
    }
    summaries = [
        SimpleNamespace(uniqueID=tc_uid, exec=_execution(f"E-{tc_uid}", status) if status else None)
        for tc_uid, status in test_cases.items()
    ]
    details = SimpleNamespace(
        key=f"K-{uid}",
        uniqueID=uid,
        testCases=summaries,
        exec=SimpleNamespace(key=f"X-{uid}") if with_exec else None,
    )
    return SimpleNamespace(details=details, test_cases=details_cases)


def _context():
    return SimpleNamespace(project_key="P", cycle_key="C")


class TestBuildPlanningImport:
    def test_sets_selected_test_cases_to_planned(self):
        catalog = {
            "S1": _set("S1", {"TC-1": ActivityStatus.NotPlanned, "TC-2": ActivityStatus.NotPlanned})
        }

        planning = build_planning_import(catalog, ["TC-1"])

        [entry] = planning.protocol
        assert entry.testCaseSetKey == "K-S1"
        assert entry.executionKey == "X-S1"
        [case] = entry.testCases
        assert case.uniqueID == "TC-1"
        assert case.testCaseExecutionKey == "E-TC-1"
        assert case.result.status is ActivityStatus.Planned
        assert [d.uniqueID for d in planning.details] == ["S1"]
        assert planning.skipped == {}

    def test_keeps_exec_status_and_verdict(self):
        catalog = {"S1": _set("S1", {"TC-1": ActivityStatus.Skipped})}
        execution = catalog["S1"].test_cases["TC-1"].exec
        execution.execStatus = ExecStatus.Blocked
        execution.verdict = VerdictStatus.ToVerify

        [entry] = build_planning_import(catalog, ["TC-1"]).protocol

        result = entry.testCases[0].result
        assert result.execStatus is ExecStatus.Blocked
        assert result.verdict is VerdictStatus.ToVerify

    def test_skips_planned_assigned_and_executed_test_cases(self):
        catalog = {
            "S1": _set(
                "S1",
                {
                    "TC-1": ActivityStatus.Planned,
                    "TC-2": ActivityStatus.Assigned,
                    "TC-3": ActivityStatus.Performed,
                    "TC-4": ActivityStatus.Running,
                },
            )
        }

        planning = build_planning_import(catalog, ["TC-1", "TC-2", "TC-3", "TC-4"])

        assert planning.protocol == planning.details == []
        assert planning.skipped == {"already planned": 2, "executed": 2}

    def test_skips_test_cases_and_sets_without_execution(self):
        catalog = {
            "S1": _set("S1", {"TC-1": None}),
            "S2": _set("S2", {"TC-2": ActivityStatus.NotPlanned}, with_exec=False),
        }

        planning = build_planning_import(catalog, ["TC-1", "TC-2"])

        assert planning.protocol == planning.details == []
        assert planning.skipped == {"no execution": 1, "set without execution": 1}

    def test_counts_test_cases_missing_from_the_report(self):
        catalog = {"S1": _set("S1", {"TC-1": ActivityStatus.NotPlanned})}

        assert build_planning_import(catalog, ["TC-1", "TC-9"]).skipped == {"not in report": 1}

    def test_marks_the_set_details_as_planned_too(self):
        catalog = {"S1": _set("S1", {"TC-1": ActivityStatus.NotPlanned})}

        [details] = build_planning_import(catalog, ["TC-1"]).details

        assert details.testCases[0].exec.status is ActivityStatus.Planned

    def test_one_entry_per_affected_set_sorted_by_uid(self):
        catalog = {
            "S2": _set("S2", {"TC-2": ActivityStatus.NotPlanned}),
            "S1": _set("S1", {"TC-1": ActivityStatus.Canceled}),
            "S3": _set("S3", {"TC-3": ActivityStatus.NotPlanned}),
        }

        planning = build_planning_import(catalog, ["TC-2", "TC-1"])

        assert [e.testCaseSetKey for e in planning.protocol] == ["K-S1", "K-S2"]
        assert [d.uniqueID for d in planning.details] == ["S1", "S2"]


@dataclass
class _Details:
    uniqueID: str
    status: ActivityStatus


def test_zip_holds_protocol_and_set_details(tmp_path):
    catalog = {"S1": _set("S1", {"TC-1": ActivityStatus.NotPlanned})}
    protocol = build_planning_import(catalog, ["TC-1"]).protocol
    path = tmp_path / "planning.zip"

    write_import_zip(protocol, [_Details("S1", ActivityStatus.Planned)], path)

    with zipfile.ZipFile(path) as zipf:
        assert sorted(zipf.namelist()) == ["S1.json", "protocol.json"]
        [entry] = json.loads(zipf.read("protocol.json"))
        details = json.loads(zipf.read("S1.json"))
    assert entry["testCaseSetKey"] == "K-S1"
    assert entry["testCases"][0]["result"]["status"] == "Planned"
    assert details == {"uniqueID": "S1", "status": "Planned"}


class TestPlanTestCases:
    async def test_imports_with_non_executed_test_cases_kept(self):
        catalog = {"S1": _set("S1", {"TC-1": ActivityStatus.NotPlanned})}
        importer = MagicMock()
        importer.trigger.return_value = True

        with (
            patch(f"{_MODULE}.write_import_zip") as write,
            patch(f"{_MODULE}.ImportJSONExecutionResults", return_value=importer) as action,
        ):
            planned = await plan_test_cases(MagicMock(), _context(), catalog, ["TC-1"])

        assert planned == 1
        write.assert_called_once()
        parameters = action.call_args.kwargs["parameters"]
        assert parameters.projectKey == "P"
        assert parameters.cycleKey == "C"
        assert parameters.importConfig.ignoreNonExecutedTestCases is False
        importer.trigger.assert_called_once()

    async def test_logs_why_selected_test_cases_were_skipped(self, caplog):
        catalog = {
            "S1": _set("S1", {"TC-1": ActivityStatus.Planned, "TC-2": ActivityStatus.Assigned}),
            "S2": _set("S2", {"TC-3": ActivityStatus.NotPlanned}, with_exec=False),
        }

        with caplog.at_level(logging.INFO, logger="testbench_ai_service"):
            await plan_test_cases(MagicMock(), _context(), catalog, ["TC-1", "TC-2", "TC-3"])

        assert (
            "Test planner skipped 3 selected test cases | already planned=2, "
            "set without execution=1 | cycle='C'" in caplog.messages
        )

    async def test_imports_nothing_when_nothing_changes(self):
        catalog = {"S1": _set("S1", {"TC-1": ActivityStatus.Planned})}

        with patch(f"{_MODULE}.ImportJSONExecutionResults") as action:
            planned = await plan_test_cases(MagicMock(), _context(), catalog, ["TC-1"])

        assert planned == 0
        action.assert_not_called()

    async def test_failed_trigger_raises(self):
        catalog = {"S1": _set("S1", {"TC-1": ActivityStatus.NotPlanned})}
        importer = MagicMock()
        importer.trigger.return_value = False

        with (
            patch(f"{_MODULE}.write_import_zip"),
            patch(f"{_MODULE}.ImportJSONExecutionResults", return_value=importer),
            pytest.raises(RuntimeError, match="cycle 'C'"),
        ):
            await plan_test_cases(MagicMock(), _context(), catalog, ["TC-1"])
