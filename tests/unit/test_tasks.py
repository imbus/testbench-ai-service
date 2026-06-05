import dataclasses
import datetime
import logging
import tempfile
import zipfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from testbench2robotframework.json_reader import TestBenchJsonReader

from testbench_ai_service.agents.test_case_set_reviewer.agent import TestCaseSetReviewer
from testbench_ai_service.config import (
    DEFAULT_AGENTS,
    AppConfig,
    LLMConfig,
    PromptConfig,
)
from testbench_ai_service.llm.base import LLMClient
from testbench_ai_service.models.agent import AgentResult, ExecutionContext
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
    def setup(self):
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
        self.mock_reviewer = TestCaseSetReviewer()
        self.mock_reviewer._get_ai_response = AsyncMock(
            side_effect=self._reviewer_get_ai_response_side_effect
        )
        self.mock_reviewer_class.return_value = self.mock_reviewer

        # ── get_prompt_model mock ─────────────────────────────────────────────
        prompt_model_patcher = patch(
            "testbench_ai_service.tasks.get_prompt_model",
            return_value="gpt-4o",
        )
        prompt_model_patcher.start()

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
            user_key=self.user_key,
            project_name=self.project_name,
            project_key=self.project_key,
            tov_key=self.tov_key,
            cycle_key=self.cycle_key,
            root_uid="iTB-TT-4091",
            language="de",
            llm_config=llm_config,
            prompt_config=self.prompt_config,
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

        yield

        reviewer_patcher.stop()
        prompt_model_patcher.stop()

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
        self.mock_reviewer._get_ai_response = AsyncMock(side_effect=Exception("service error"))

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
