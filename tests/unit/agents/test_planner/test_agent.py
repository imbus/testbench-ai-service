import asyncio
import json
import logging
import time
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from testbench_ai_service.agents.test_planner import planner
from testbench_ai_service.agents.test_planner.agent import TestPlannerAgent
from testbench_ai_service.agents.test_planner.model import PlannerTestCase, TestPlannerArgs
from testbench_ai_service.config import PROMPTS_DIR
from testbench_ai_service.llm.base import LLMProvider, NoLLMClient
from testbench_ai_service.models.agent import ExecutionContext
from testbench_ai_service.models.config import LLMConfig, PromptConfig
from testbench_ai_service.models.language import LanguageOption
from testbench_ai_service.models.testbench import ActivityStatus
from testbench_ai_service.utils.i18n import load_translations

_MODULE = "testbench_ai_service.agents.test_planner.agent"


def _context(variant=None, variables=None, **overrides):
    fields = {
        "user_key": "U1",
        "project_key": "P1",
        "project_name": "Project",
        "tov_key": "T1",
        "cycle_key": "C1",
        "language": LanguageOption.ENGLISH,
        "llm_config": LLMConfig(provider=LLMProvider.OPENAI),
        "prompt_config": PromptConfig(
            file=PROMPTS_DIR / "en" / "test_planner" / "prompt.yaml",
            variant=variant,
            vars=variables,
        ),
        "templates_dir": "templates",
    }
    fields.update(overrides)
    return ExecutionContext(**fields)


def _conn():
    conn = MagicMock()
    conn.server_version = [4, 1]
    return conn


def _case(i, status=ActivityStatus.NotPlanned, minutes=10.0, reqs=()):
    return PlannerTestCase(
        unique_id=f"TC-{i}",
        key=str(i),
        set_key="S",
        set_name=f"Set {i}",
        path=f"/{i}",
        text=f"text {i}",
        planned_minutes=minutes,
        status=status,
        requirement_keys=frozenset(reqs),
    )


@pytest.fixture(autouse=True)
def translations():
    load_translations()


@pytest.fixture
def json_tov():
    with patch(f"{_MODULE}.is_json_based_tov", return_value=True):
        yield


@contextmanager
def _collect(cases):
    with (
        patch(f"{_MODULE}.load_catalog", return_value=CATALOG),
        patch(f"{_MODULE}.test_cases_from_catalog", return_value=cases),
    ):
        yield


CATALOG = {"S": "catalog"}


@pytest.fixture(autouse=True)
def plan_test_cases():
    with patch(f"{_MODULE}.plan_test_cases", new=AsyncMock(return_value=0)) as plan:
        yield plan


class TestClassSetup:
    def test_needs_no_llm_and_uses_its_args(self):
        assert TestPlannerAgent.USES_LLM is False
        assert TestPlannerAgent.ARGS_CLASS is TestPlannerArgs
        assert isinstance(TestPlannerAgent().args, TestPlannerArgs)


@pytest.mark.usefixtures("json_tov")
class TestPrecheck:
    async def test_passes_with_candidates_as_items(self):
        agent = TestPlannerAgent()
        cases = [_case(0), _case(1), _case(2, status=ActivityStatus.Performed)]

        with _collect(cases):
            result = await agent.precheck(_context(), _conn())

        assert result.passed
        assert result.items == ["TC-0", "TC-1"]
        assert result.warnings == []

    async def test_logs_how_many_test_cases_were_looked_at(self, caplog):
        cases = [_case(0), _case(1), _case(2, status=ActivityStatus.Performed)]

        with _collect(cases), caplog.at_level(logging.INFO, logger="testbench_ai_service"):
            await TestPlannerAgent().precheck(_context(), _conn())

        assert (
            "Test planner looked at 3 test cases, 2 of them not executed yet | cycle='C1'"
            in caplog.messages
        )

    async def test_missing_tov_fails(self):
        result = await TestPlannerAgent().precheck(_context(tov_key=None), _conn())

        assert not result.passed
        assert "version" in result.warnings[0]

    async def test_missing_cycle_fails(self):
        result = await TestPlannerAgent().precheck(_context(cycle_key=None), _conn())

        assert not result.passed
        assert "cycle" in result.warnings[0]

    async def test_xml_tov_fails(self):
        with patch(f"{_MODULE}.is_json_based_tov", return_value=False):
            result = await TestPlannerAgent().precheck(_context(), _conn())

        assert not result.passed
        assert "XML" in result.warnings[0]

    async def test_old_testbench_fails(self):
        conn = _conn()
        conn.server_version = [4, 0]

        result = await TestPlannerAgent().precheck(_context(), conn)

        assert not result.passed

    async def test_unknown_variant_fails(self):
        result = await TestPlannerAgent().precheck(_context(variant="Nope"), _conn())

        assert not result.passed
        assert "Nope" in result.warnings[0]

    async def test_invalid_vars_fail(self):
        result = await TestPlannerAgent().precheck(
            _context(variant="Count", variables={"count": "-1"}), _conn()
        )

        assert not result.passed
        assert result.warnings[0].startswith("Invalid parameters")

    async def test_all_executed_fails(self):
        cases = [_case(0, status=ActivityStatus.Performed), _case(1, status=ActivityStatus.Running)]

        with _collect(cases):
            result = await TestPlannerAgent().precheck(_context(), _conn())

        assert not result.passed
        assert "only 0 test cases" in result.warnings[0]

    async def test_coverage_warns_about_missing_links(self):
        with _collect([_case(0, reqs=("R1",)), _case(1)]):
            result = await TestPlannerAgent().precheck(
                _context(variant="Requirement coverage"), _conn()
            )

        assert result.passed
        assert result.warnings == [
            "1 of 2 test cases have no requirement links; the coverage is of limited meaning."
        ]

    async def test_budget_warns_about_missing_durations(self):
        with _collect([_case(0, minutes=0), _case(1)]):
            result = await TestPlannerAgent().precheck(_context(variant="Time budget"), _conn())

        assert result.warnings == [
            "1 of 2 test cases have no planned duration; they count as 0 minutes."
        ]


@pytest.mark.usefixtures("json_tov")
class TestRun:
    async def test_logs_the_plan_as_json(self, caplog, tmp_path):
        agent = TestPlannerAgent(TestPlannerArgs(embedding={"cache_dir": str(tmp_path)}))
        cases = [_case(0), _case(1), _case(2)]
        client = MagicMock()
        client.embed = AsyncMock(return_value=np.eye(3, dtype=np.float32))
        client.close = AsyncMock()
        context = _context(variant="Count", variables={"count": "2"})

        with _collect(cases):
            await agent.precheck(context, _conn())
        with (
            patch(f"{_MODULE}.create_embedding_client", return_value=client),
            caplog.at_level(logging.INFO, logger="testbench_ai_service"),
        ):
            await agent.run(context, _conn(), NoLLMClient(), ["TC-0", "TC-1", "TC-2"])

        client.close.assert_awaited_once()
        record = next(r for r in caplog.records if "Test planner selection" in r.getMessage())
        payload = json.loads(record.getMessage().split("\n", 1)[1])
        assert payload["selected"] == 2
        assert payload["total"] == 3
        assert payload["mode"] == "count"
        assert [e["unique_id"] for e in payload["selection"]] == ["TC-0", "TC-1"]

    async def test_sets_the_selection_to_planned(self, plan_test_cases, tmp_path):
        agent = TestPlannerAgent(TestPlannerArgs(embedding={"cache_dir": str(tmp_path)}))
        client = MagicMock(
            embed=AsyncMock(return_value=np.eye(3, dtype=np.float32)), close=AsyncMock()
        )
        context = _context(variant="Count", variables={"count": "2"})
        conn = _conn()

        with _collect([_case(0), _case(1), _case(2)]):
            await agent.precheck(context, conn)
        with patch(f"{_MODULE}.create_embedding_client", return_value=client):
            await agent.run(context, conn, NoLLMClient(), ["TC-0", "TC-1", "TC-2"])

        plan_test_cases.assert_awaited_once_with(conn, context, CATALOG, ["TC-0", "TC-1"])

    async def test_cutoff_notes_become_translated_warnings(self, caplog, tmp_path):
        agent = TestPlannerAgent(TestPlannerArgs(embedding={"cache_dir": str(tmp_path)}))
        client = MagicMock(
            embed=AsyncMock(return_value=np.eye(2, dtype=np.float32)), close=AsyncMock()
        )
        context = _context(variant="Requirement coverage")

        with _collect([_case(0), _case(1)]):
            await agent.precheck(context, _conn())
        with (
            patch(f"{_MODULE}.create_embedding_client", return_value=client),
            caplog.at_level(logging.INFO, logger="testbench_ai_service"),
        ):
            await agent.run(context, _conn(), NoLLMClient(), ["TC-0", "TC-1"])

        record = next(r for r in caplog.records if "Test planner selection" in r.getMessage())
        warnings = json.loads(record.getMessage().split("\n", 1)[1])["warnings"]
        assert warnings[-1].startswith("No test case has requirement links")

    async def test_run_without_precheck_raises(self):
        with pytest.raises(RuntimeError, match="precheck"):
            await TestPlannerAgent().run(_context(), _conn(), NoLLMClient(), [])

    async def test_embedding_client_is_closed_on_failure(self, tmp_path):
        agent = TestPlannerAgent(TestPlannerArgs(embedding={"cache_dir": str(tmp_path)}))
        client = MagicMock(embed=AsyncMock(side_effect=RuntimeError("api down")), close=AsyncMock())

        with _collect([_case(0), _case(1)]):
            await agent.precheck(_context(), _conn())
        with (
            patch(f"{_MODULE}.create_embedding_client", return_value=client),
            pytest.raises(RuntimeError, match="api down"),
        ):
            await agent.run(_context(), _conn(), NoLLMClient(), [])

        client.close.assert_awaited_once()


@pytest.mark.usefixtures("json_tov")
async def test_run_keeps_the_event_loop_responsive(tmp_path):

    real_build_plan = planner.build_plan

    def slow_build_plan(*args, **kwargs):
        time.sleep(0.3)  # stands in for the CPU-bound selection of a large suite
        return real_build_plan(*args, **kwargs)

    agent = TestPlannerAgent(TestPlannerArgs(embedding={"cache_dir": str(tmp_path)}))
    client = MagicMock(embed=AsyncMock(return_value=np.eye(2, dtype=np.float32)), close=AsyncMock())
    ticks = 0

    async def ticker():
        nonlocal ticks
        while True:
            await asyncio.sleep(0.02)
            ticks += 1

    with _collect([_case(0), _case(1)]):
        await agent.precheck(_context(), _conn())
    with (
        patch(f"{_MODULE}.create_embedding_client", return_value=client),
        patch(f"{_MODULE}.build_plan", side_effect=slow_build_plan),
    ):
        task = asyncio.create_task(ticker())
        await agent.run(_context(), _conn(), NoLLMClient(), [])
        task.cancel()

    assert ticks >= 5
