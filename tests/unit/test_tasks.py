import asyncio
import dataclasses
import datetime
import logging
import tempfile
import zipfile
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from testbench2robotframework.json_reader import TestBenchJsonReader

from testbench_ai_service.agents.test_case_set_reviewer.agent import TestCaseSetReviewer
from testbench_ai_service.config import DEFAULT_AGENTS, AppConfig
from testbench_ai_service.jobs.handle import current_job
from testbench_ai_service.jobs.store import JobStore
from testbench_ai_service.llm.base import LLMClient, NoLLMClient
from testbench_ai_service.log import LogContextFilter, log_run_id
from testbench_ai_service.log import logger as service_logger
from testbench_ai_service.models.agent import AgentResult, ExecutionContext
from testbench_ai_service.models.config import LLMConfig, PromptConfig
from testbench_ai_service.models.testbench import (
    OptionalUser,
    RichTextInfo,
    SpecificationDetailsForUpdate,
)
from testbench_ai_service.tasks import run_agent
from testbench_ai_service.utils.config import get_llm_config
from testbench_ai_service.utils.html_utils import has_visible_text, strip_html_body_tags
from testbench_ai_service.utils.i18n import get_translation, load_translations
from testbench_ai_service.utils.testbench_helpers import test_case_set_as_str as _tcs_as_str
from tests.unit.helpers.data import get_test_data_path


class TestRunAgentReviewTask:
    """run_agent runs the full review pipeline and writes back results via PATCH."""

    @pytest.fixture(autouse=True)
    def setup(self, request):
        # ── TB connection mock ────────────────────────────────────────────────
        self.mock_tb_connection = MagicMock()
        self.mock_tb_connection.server_url = "https://localhost:9443/api/"
        self.mock_tb_connection.session.get.side_effect = self._tb_session_get_side_effect
        self.mock_tb_connection.get_json_report_data.side_effect = (
            self._tb_get_json_report_data_side_effect
        )
        self.mock_tb_connection.get_project_test_case_set.side_effect = (
            self._tb_get_project_test_case_set_side_effect
        )

        # ── Reviewer mock ─────────────────────────────────────────────────────
        reviewer_patcher = patch(
            "testbench_ai_service.agents.test_case_set_reviewer.agent.TestCaseSetReviewer"
        )
        self.mock_reviewer_class = reviewer_patcher.start()
        request.addfinalizer(reviewer_patcher.stop)
        self.mock_reviewer = TestCaseSetReviewer()
        self.mock_reviewer.get_ai_response = AsyncMock(
            side_effect=self._reviewer_get_ai_response_side_effect
        )
        self.mock_reviewer_class.return_value = self.mock_reviewer

        # ── get_prompt_model mock ─────────────────────────────────────────────
        prompt_model_patcher = patch(
            "testbench_ai_service.tasks.get_prompt_model",
            return_value="gpt-4o",
        )
        prompt_model_patcher.start()
        # addfinalizer (not yield + teardown) is required here: this fixture can
        # raise during setup (e.g. AppConfig construction below), and a post-yield
        # teardown never runs in that case, which previously let this mock.patch()
        # leak out and corrupt TestCaseSetReviewer for every later test.
        request.addfinalizer(prompt_model_patcher.stop)  # noqa: PT021

        # ── LLM factory mock ──────────────────────────────────────────────────
        self.mock_llm_client = AsyncMock()
        self.mock_llm_factory = MagicMock()
        self.mock_llm_factory.get_client.return_value = self.mock_llm_client

        # ── Config ────────────────────────────────────────────────────────────
        self.prompt_config = DEFAULT_AGENTS["test_case_set_reviewer"].prompt
        with patch("testbench_ai_service.config.validate_tb_server_url"):
            self.app_config = AppConfig(tb_server_url=self.mock_tb_connection.server_url)
        self.app_config.agents["test_case_set_reviewer"].prompt = self.prompt_config

        # ── Test identifiers ──────────────────────────────────────────────────
        self.user_key = "1"
        self.project_key = "1"
        self.tov_key = "2"
        self.cycle_key = "3"
        self.project_name = "Car Configurator"

        # ── Execution context ─────────────────────────────────────────────────
        llm_config = get_llm_config(
            config=self.app_config, project_name=self.project_name, request_config=None
        )
        self.context = ExecutionContext(
            agent_key="test_agent",
            user_key=self.user_key,
            project_name=self.project_name,
            project_key=self.project_key,
            tov_key=self.tov_key,
            cycle_key=self.cycle_key,
            root_uid="iTB-TT-4091",
            language="de",
            llm_config=llm_config,
            prompt_config=self.prompt_config,
            templates_dir=self.app_config.templates_dir,
        )

        # ── Load test case sets from the shared report fixture ────────────────
        with tempfile.TemporaryDirectory() as report_dir:
            report_zip = zipfile.ZipFile(get_test_data_path("cycle_report.zip"))
            report_zip.extractall(report_dir)
            reader = TestBenchJsonReader(report_dir)
            self.tcs_catalog = reader.get_test_case_set_catalog()
            self.test_case_sets = list(self.tcs_catalog.values())

        self.items = self.test_case_sets

        self.tcs_strings = {
            tcs.details.uniqueID: _tcs_as_str(self.tcs_catalog[tcs.details.uniqueID])
            for tcs in self.test_case_sets[:3]
        }

        self.review_responses = {
            self.test_case_sets[0].details.uniqueID: AgentResult(result="TCS1 Review Notes"),
            self.test_case_sets[1].details.uniqueID: AgentResult(result="TCS2 review notes"),
            self.test_case_sets[2].details.uniqueID: AgentResult(result=""),
        }

        self.patch_url_prefix = (
            f"{self.mock_tb_connection.server_url}2/projects/{self.project_key}/specifications/"
        )

        load_translations()

    # ── Tests ─────────────────────────────────────────────────────────────────

    async def test_review_task_completes_and_patches_all_test_case_sets(self):
        """Happy path: all test case sets are patched with started + result payloads."""
        fake_now = datetime.datetime(2025, 1, 1, 12, 0, 0, tzinfo=datetime.timezone.utc)
        with patch("testbench_ai_service.utils.time_utils.datetime") as mock_datetime:
            mock_datetime.now.return_value = fake_now
            await run_agent(
                agent_key="test_case_set_reviewer",
                agent=self.mock_reviewer,
                context=self.context,
                conn=self.mock_tb_connection,
                llm_factory=self.mock_llm_factory,
                item_ids=[tcs.details.uniqueID for tcs in self.test_case_sets],
            )

        current_time = fake_now.strftime("%Y-%m-%d %H:%M:%S")
        for tcs in self.test_case_sets:
            review_started_msg = get_translation(
                "test_case_set_reviewer.run.started", self.context.language
            )
            previous_comment = strip_html_body_tags(tcs.details.spec.reviewComment)
            if has_visible_text(previous_comment):
                expected_started_html = (
                    f"<html><body>{current_time} - {review_started_msg}"
                    f"<br/><br/>{previous_comment}</body></html>"
                )
            else:
                expected_started_html = (
                    f"<html><body>{current_time} - {review_started_msg}</body></html>"
                )
            started_payload = SpecificationDetailsForUpdate(
                locker=OptionalUser(optional=self.user_key),
                reviewer=OptionalUser(optional=self.user_key),
                reviewComment=RichTextInfo(html=expected_started_html, images=[]),
            ).model_dump(exclude_unset=True)
            self.mock_tb_connection.session.patch.assert_any_call(
                f"{self.patch_url_prefix}{tcs.details.spec.key}", json=started_payload
            )

            heading = get_translation(
                "test_case_set_reviewer.run.result_heading", self.context.language
            )
            notes = self.review_responses[tcs.details.uniqueID].result or get_translation(
                "test_case_set_reviewer.run.no_notes", self.context.language
            )
            disclaimer = get_translation("shared.run.disclaimer", self.context.language)
            notes_html = notes.replace("\n", "<br/>")
            disclaimer_html = (
                f"<div style='padding-top: 5px;'><div style='border-top: 1px solid black; "
                f"width: 218px; font-size: 10px;'>{disclaimer}</div></div>"
            )
            if has_visible_text(previous_comment):
                expected_result_html = (
                    f"<html><body><b>{heading} - {current_time}</b><br/>{notes_html}"
                    f"{disclaimer_html}<br/>{previous_comment}</body></html>"
                )
            else:
                expected_result_html = (
                    f"<html><body><b>{heading} - {current_time}</b><br/>{notes_html}"
                    f"{disclaimer_html}</body></html>"
                )
            result_payload = SpecificationDetailsForUpdate(
                locker=OptionalUser(optional=None),
                reviewer=OptionalUser(optional=self.user_key),
                reviewComment=RichTextInfo(html=expected_result_html, images=[]),
            ).model_dump(exclude_unset=True)
            self.mock_tb_connection.session.patch.assert_any_call(
                f"{self.patch_url_prefix}{tcs.details.spec.key}", json=result_payload
            )

    async def test_patch_failure_is_logged_as_error(self, caplog):
        """When a PATCH call raises, run_agent logs the error and continues."""
        self.mock_tb_connection.session.patch.side_effect = Exception("patch error")

        fake_now = datetime.datetime(2025, 1, 1, 12, 0, 0, tzinfo=datetime.timezone.utc)
        with patch("testbench_ai_service.utils.time_utils.datetime") as mock_datetime:
            mock_datetime.now.return_value = fake_now
            with caplog.at_level(logging.ERROR, logger="testbench_ai_service"):
                await run_agent(
                    agent_key="test_case_set_reviewer",
                    agent=self.mock_reviewer,
                    context=self.context,
                    conn=self.mock_tb_connection,
                    llm_factory=self.mock_llm_factory,
                    item_ids=[tcs.details.uniqueID for tcs in self.test_case_sets],
                )

        assert any(r.levelno >= logging.ERROR for r in caplog.records)

        current_time = fake_now.strftime("%Y-%m-%d %H:%M:%S")
        for tcs in self.test_case_sets:
            heading = get_translation(
                "test_case_set_reviewer.run.failed_heading", self.context.language
            )
            error_message = get_translation("shared.run.error_message", self.context.language)
            previous_comment = strip_html_body_tags(tcs.details.spec.reviewComment)
            if has_visible_text(previous_comment):
                failed_html = (
                    f"<html><body><b>{heading} - {current_time}</b>"
                    f"<br/>{error_message}<br/>{previous_comment}</body></html>"
                )
            else:
                failed_html = (
                    f"<html><body><b>{heading} - {current_time}</b>"
                    f"<br/>{error_message}</body></html>"
                )
            failed_payload = SpecificationDetailsForUpdate(
                locker=OptionalUser(optional=None),
                reviewer=OptionalUser(optional=self.user_key),
                reviewComment=RichTextInfo(html=failed_html, images=[]),
            ).model_dump(exclude_unset=True)
            self.mock_tb_connection.session.patch.assert_any_call(
                f"{self.patch_url_prefix}{tcs.details.spec.key}", json=failed_payload
            )

        self.mock_tb_connection.session.patch.side_effect = None

    async def test_reviewer_failure_is_logged_as_error(self, caplog):
        """When the AI reviewer raises, run_agent logs the error and patches failure."""
        self.mock_reviewer.get_ai_response = AsyncMock(side_effect=Exception("service error"))

        fake_now = datetime.datetime(2025, 1, 1, 12, 0, 0, tzinfo=datetime.timezone.utc)
        with patch("testbench_ai_service.utils.time_utils.datetime") as mock_datetime:
            mock_datetime.now.return_value = fake_now
            with caplog.at_level(logging.ERROR, logger="testbench_ai_service"):
                await run_agent(
                    agent_key="test_case_set_reviewer",
                    agent=self.mock_reviewer,
                    context=self.context,
                    conn=self.mock_tb_connection,
                    llm_factory=self.mock_llm_factory,
                    item_ids=[tcs.details.uniqueID for tcs in self.test_case_sets],
                )

        assert any(r.levelno >= logging.ERROR for r in caplog.records)

        current_time = fake_now.strftime("%Y-%m-%d %H:%M:%S")
        for tcs in self.test_case_sets:
            heading = get_translation(
                "test_case_set_reviewer.run.failed_heading", self.context.language
            )
            error_message = get_translation("shared.run.error_message", self.context.language)
            previous_comment = strip_html_body_tags(tcs.details.spec.reviewComment)
            if has_visible_text(previous_comment):
                failed_html = (
                    f"<html><body><b>{heading} - {current_time}</b>"
                    f"<br/>{error_message}<br/>{previous_comment}</body></html>"
                )
            else:
                failed_html = (
                    f"<html><body><b>{heading} - {current_time}</b>"
                    f"<br/>{error_message}</body></html>"
                )
            failed_payload = SpecificationDetailsForUpdate(
                locker=OptionalUser(optional=None),
                reviewer=OptionalUser(optional=self.user_key),
                reviewComment=RichTextInfo(html=failed_html, images=[]),
            ).model_dump(exclude_unset=True)
            self.mock_tb_connection.session.patch.assert_any_call(
                f"{self.patch_url_prefix}{tcs.details.spec.key}", json=failed_payload
            )

    # ── Side-effect helpers ───────────────────────────────────────────────────

    def _tb_session_get_side_effect(self, url: str):
        if url == f"{self.mock_tb_connection.server_url}2/login/session":
            mock_response = MagicMock()
            mock_response.json.return_value = {"userKey": self.user_key}
            return mock_response
        return None

    def _tb_get_json_report_data_side_effect(self, project_key: str, temp_name: str):
        if project_key == self.project_key:
            return (get_test_data_path("cycle_report.zip")).read_bytes()
        return None

    def _tb_get_project_test_case_set_side_effect(self, project_key: str, test_case_set_key: str):
        if project_key == self.project_key:
            for tcs in self.test_case_sets:
                if tcs.details.key == test_case_set_key:
                    return dataclasses.asdict(tcs.details)
        return None

    def _reviewer_get_ai_response_side_effect(
        self,
        llm_client: LLMClient,
        llm_config: LLMConfig,
        prompt_config: PromptConfig,
        agent_data: dict | None = None,
    ):
        tcs_str = (agent_data or {}).get("test_case_set", "")
        for uid, s in self.tcs_strings.items():
            if tcs_str == s:
                return self.review_responses[uid]
        return None


class _Capture(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.records: list[logging.LogRecord] = []
        self.addFilter(LogContextFilter())

    def emit(self, record):
        self.records.append(record)


class _LoggingAgent:
    def __init__(self, label: str):
        self.label = label

    async def run(self, context, conn, llm_client, item_ids):
        service_logger.info("agent %s step 1", self.label)
        await asyncio.sleep(0)  # let the other run interleave
        await asyncio.to_thread(service_logger.info, "agent %s in thread", self.label)
        service_logger.info("agent %s step 2", self.label)


def _ctx(user_key: str):
    return SimpleNamespace(
        user_key=user_key,
        project_key=f"p-{user_key}",
        project_name="P",
        llm_config=SimpleNamespace(model=None),
        prompt_config=None,
    )


class TestRunAgentLogContext:
    @pytest.fixture
    def capture(self):
        handler = _Capture()
        previous = service_logger.level
        service_logger.setLevel(logging.DEBUG)
        service_logger.addHandler(handler)
        yield handler
        service_logger.removeHandler(handler)
        service_logger.setLevel(previous)

    async def _run(self, user_key):
        factory = MagicMock()
        with patch("testbench_ai_service.tasks.get_prompt_model", return_value=None):
            await run_agent(
                agent_key="reviewer",
                agent=_LoggingAgent(user_key),
                context=_ctx(user_key),
                conn=MagicMock(),
                llm_factory=factory,
                item_ids=[],
            )

    async def test_every_record_of_the_run_is_tagged(self, capture):
        await self._run("u-1")
        run_records = [r for r in capture.records if r.scope == "user"]
        assert len(run_records) == len(capture.records)
        assert {r.user_key for r in run_records} == {"u-1"}
        assert {r.agent for r in run_records} == {"reviewer"}
        assert {r.project_key for r in run_records} == {"p-u-1"}
        run_ids = {r.run_id for r in run_records}
        assert len(run_ids) == 1
        assert len(run_ids.pop()) == 32
        assert any("in thread" in r.getMessage() for r in run_records)

    async def test_context_is_gone_after_the_run(self, capture):
        await self._run("u-1")
        service_logger.info("afterwards")
        assert capture.records[-1].scope == "service"

    async def test_concurrent_runs_of_different_users_do_not_mix(self, capture):
        # Review Focus 2.
        await asyncio.gather(self._run("u-1"), self._run("u-2"))
        for record in capture.records:
            message = record.getMessage()
            if "agent u-1" in message:
                assert record.user_key == "u-1"
            if "agent u-2" in message:
                assert record.user_key == "u-2"
        assert {r.user_key for r in capture.records} == {"u-1", "u-2"}


class TestRunAgentWithoutLLM:
    async def test_agent_without_llm_gets_no_llm_client(self):
        agent = MagicMock()
        agent.USES_LLM = False
        agent.run = AsyncMock()
        llm_factory = MagicMock()
        llm_factory.get_client.side_effect = AssertionError("must not be called")

        await run_agent(
            agent_key="test_planner",
            agent=agent,
            context=MagicMock(project_name="P"),
            conn=MagicMock(),
            llm_factory=llm_factory,
            item_ids=["TC-1"],
        )

        agent.run.assert_awaited_once()
        assert isinstance(agent.run.call_args.kwargs["llm_client"], NoLLMClient)

    async def test_agents_without_the_flag_still_get_the_factory_client(self):
        agent = MagicMock(spec=["run"])  # no USES_LLM attribute, like an old custom agent
        agent.run = AsyncMock()
        llm_factory = MagicMock()

        with patch("testbench_ai_service.tasks.get_prompt_model", return_value="gpt-5.5"):
            await run_agent(
                agent_key="custom",
                agent=agent,
                context=MagicMock(project_name="P"),
                conn=MagicMock(),
                llm_factory=llm_factory,
                item_ids=[],
            )

        assert agent.run.call_args.kwargs["llm_client"] is llm_factory.get_client.return_value

    async def test_the_configured_model_picks_the_client(self):
        # An agent model of another provider than the prompt's default must
        # reach that provider's client.
        agent = MagicMock(spec=["run"])
        agent.run = AsyncMock()
        llm_factory = MagicMock()
        context = MagicMock(project_name="P")
        context.llm_config.model = "claude-sonnet-5"

        with patch("testbench_ai_service.tasks.get_prompt_model", return_value="gpt-5.5"):
            await run_agent(
                agent_key="custom",
                agent=agent,
                context=context,
                conn=MagicMock(),
                llm_factory=llm_factory,
                item_ids=[],
            )

        assert llm_factory.get_client.call_args.kwargs["prompt_model"] == "claude-sonnet-5"

    async def test_no_llm_client_refuses_queries(self):
        with pytest.raises(RuntimeError, match="does not use an LLM"):
            await NoLLMClient().query_llm("m", [])


class TestRunAgentJobLifecycle:
    """run_agent ends the job it was given and exposes it to the agent."""

    @pytest.fixture
    def store(self, tmp_path):
        store = JobStore(tmp_path / "jobs.sqlite")
        store.create(
            "j1",
            agent_key="a",
            user_key="u1",
            project_key="p",
            project_name="P",
            root_key=None,
            item_ids=["i"],
            warnings=[],
        )
        return store

    @pytest.fixture
    def agent(self):
        agent = MagicMock()
        agent.USES_LLM = False
        agent.run = AsyncMock()
        return agent

    @pytest.fixture
    def ctx(self):
        return MagicMock(project_name="P", user_key="u1", project_key="p")

    async def _run(self, agent, ctx, store):
        await run_agent(
            "a", agent, ctx, MagicMock(), MagicMock(), ["i"], job_id="j1", job_store=store
        )

    async def test_successful_run_marks_succeeded(self, agent, ctx, store):
        await self._run(agent, ctx, store)
        job = store.get("j1", "u1")
        assert job.status == "succeeded"
        assert job.error is None

    async def test_exception_marks_failed_with_repr(self, agent, ctx, store):
        agent.run.side_effect = RuntimeError("boom")
        await self._run(agent, ctx, store)
        job = store.get("j1", "u1")
        assert job.status == "failed"
        assert "boom" in job.error

    async def test_long_error_is_truncated(self, agent, ctx, store):
        agent.run.side_effect = RuntimeError("x" * 2000)
        await self._run(agent, ctx, store)
        assert len(store.get("j1", "u1").error) <= 500

    async def test_agent_fail_then_normal_return_stays_failed(self, agent, ctx, store):
        async def run(**_):
            await current_job().fail("no requirement")

        agent.run.side_effect = run
        await self._run(agent, ctx, store)
        job = store.get("j1", "u1")
        assert (job.status, job.error) == ("failed", "no requirement")

    async def test_agent_fail_then_raise_keeps_fail_message(self, agent, ctx, store):
        async def run(**_):
            await current_job().fail("first")
            raise RuntimeError("second")

        agent.run.side_effect = run
        await self._run(agent, ctx, store)
        job = store.get("j1", "u1")
        assert (job.status, job.error) == ("failed", "first")

    async def test_job_id_is_the_log_run_id(self, agent, ctx, store, caplog):
        run_ids = []

        class Spy(logging.Filter):
            def filter(self, record):
                if record.getMessage().startswith("Agent started"):
                    run_ids.append(log_run_id.get())
                return True

        spy = Spy()
        service_logger.addFilter(spy)
        try:
            with caplog.at_level(logging.INFO):
                await self._run(agent, ctx, store)
        finally:
            service_logger.removeFilter(spy)
        assert run_ids == ["j1"]

    async def test_without_job_store_behaves_as_before(self, agent, ctx):
        await run_agent("a", agent, ctx, MagicMock(), MagicMock(), ["i"])
        agent.run.assert_awaited_once()
