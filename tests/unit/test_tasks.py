import dataclasses
import datetime
import tempfile
import unittest
import zipfile
from unittest.mock import AsyncMock, MagicMock, patch

from testbench2robotframework.json_reader import TestBenchJsonReader

from testbench_ai_service.config import (
    DEFAULT_USECASES,
    AppConfig,
    LLMConfig,
    PromptConfig,
)
from testbench_ai_service.llm.base import LLMClient
from testbench_ai_service.log import logger
from testbench_ai_service.models.testbench import (
    OptionalUser,
    RichTextInfo,
    SpecificationDetailsForUpdate,
)
from testbench_ai_service.models.usecase import ExecutionContext, UseCaseResult
from testbench_ai_service.tasks import run_usecase
from testbench_ai_service.usecases.test_case_set_reviews.service import TestCaseSetReviewer
from testbench_ai_service.usecases.test_case_set_reviews.utils import get_test_case_set_as_string
from testbench_ai_service.utils.config import get_llm_config
from testbench_ai_service.utils.i18n import get_translation, load_translations
from testbench_ai_service.utils.string_processor import strip_html_body_tags
from tests.unit.helpers.data import get_test_data_path


class TestRunUsecaseReviewTask(unittest.IsolatedAsyncioTestCase):
    """run_usecase runs the full review pipeline and writes back results via PATCH."""

    def setUp(self):
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
        self.reviewer_patcher = patch(
            "testbench_ai_service.usecases.test_case_set_reviews.service.TestCaseSetReviewer"
        )
        self.mock_reviewer_class = self.reviewer_patcher.start()
        self.mock_reviewer = TestCaseSetReviewer()
        self.mock_reviewer._get_ai_response = AsyncMock(
            side_effect=self._reviewer_get_ai_response_side_effect
        )
        self.mock_reviewer_class.return_value = self.mock_reviewer

        # ── LLM factory mock ──────────────────────────────────────────────────
        self.mock_llm_client = AsyncMock()
        self.mock_llm_factory = MagicMock()
        self.mock_llm_factory.get_client.return_value = self.mock_llm_client

        # ── Config ────────────────────────────────────────────────────────────
        self.prompt_config = DEFAULT_USECASES["test_case_set_reviews"].prompt
        self.app_config = AppConfig(tb_server_url=self.mock_tb_connection.server_url)
        self.app_config.usecases["test_case_set_reviews"].prompt = self.prompt_config

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

        # Pre-compute expected string representations for AI response routing
        self.tcs_strings = {
            tcs.details.uniqueID: get_test_case_set_as_string(
                self.tcs_catalog[tcs.details.uniqueID]
            )
            for tcs in self.test_case_sets[:3]
        }

        self.review_responses = {
            self.test_case_sets[0].details.uniqueID: UseCaseResult(result="TCS1 Review Notes"),
            self.test_case_sets[1].details.uniqueID: UseCaseResult(result="TCS2 review notes"),
            self.test_case_sets[2].details.uniqueID: UseCaseResult(result=""),
        }

        self.patch_url_prefix = (
            f"{self.mock_tb_connection.server_url}2/projects/{self.project_key}/specifications/"
        )

        load_translations()

    def tearDown(self):
        self.reviewer_patcher.stop()

    # ── Tests ─────────────────────────────────────────────────────────────────

    async def test_review_task_completes_and_patches_all_test_case_sets(self):
        """Happy path: all test case sets are patched with started + result payloads."""
        fake_now = datetime.datetime(2025, 1, 1, 12, 0, 0, tzinfo=datetime.timezone.utc)
        with patch(
            "testbench_ai_service.usecases.test_case_set_reviews.utils.datetime"
        ) as mock_datetime:
            mock_datetime.now.return_value = fake_now
            await run_usecase(
                usecase="test_case_set_reviews",
                usecase_service=self.mock_reviewer,
                context=self.context,
                conn=self.mock_tb_connection,
                llm_factory=self.mock_llm_factory,
                items=self.items,
            )

        current_time = fake_now.strftime("%Y-%m-%d %H:%M:%S")
        for tcs in self.test_case_sets:
            # Assert "review started" PATCH
            review_started_msg = "KI Review gestartet ..."
            previous_comment = strip_html_body_tags(tcs.details.spec.reviewComment)
            expected_started_html = (
                f"<html><body>{current_time} - {review_started_msg}"
                f"<br/><br/>{previous_comment}</body></html>"
            )
            started_payload = SpecificationDetailsForUpdate(
                locker=OptionalUser(optional=self.user_key),
                reviewer=OptionalUser(optional=self.user_key),
                reviewComment=RichTextInfo(html=expected_started_html, images=[]),
            ).model_dump(exclude_unset=True)
            self.mock_tb_connection.session.patch.assert_any_call(
                f"{self.patch_url_prefix}{tcs.details.spec.key}", json=started_payload
            )

            # Assert "review result" PATCH
            heading = "KI Review"
            notes = self.review_responses[tcs.details.uniqueID].result or "Keine Review Anmerkungen"
            disclaimer = get_translation("disclaimer", self.context.language)
            notes_html = notes.replace("\n", "<br/>")
            expected_result_html = (
                f"<html><body><b>{heading} - {current_time}</b><br/>{notes_html}"
                f"<div style='padding: 5px;'><div style='border-top: 1px solid black; "
                f"width: 50%; font-size: 10px;'>{disclaimer}</div></div>"
                f"<br/>{previous_comment}</body></html>"
            )
            result_payload = SpecificationDetailsForUpdate(
                locker=OptionalUser(optional=None),
                reviewer=OptionalUser(optional=self.user_key),
                reviewComment=RichTextInfo(html=expected_result_html, images=[]),
            ).model_dump(exclude_unset=True)
            self.mock_tb_connection.session.patch.assert_any_call(
                f"{self.patch_url_prefix}{tcs.details.spec.key}", json=result_payload
            )

    async def test_patch_failure_is_logged_as_error(self):
        """When a PATCH call raises, run_usecase logs the error and continues."""
        self.mock_tb_connection.session.patch.side_effect = Exception("patch error")

        fake_now = datetime.datetime(2025, 1, 1, 12, 0, 0, tzinfo=datetime.timezone.utc)
        with patch(
            "testbench_ai_service.usecases.test_case_set_reviews.utils.datetime"
        ) as mock_datetime:
            mock_datetime.now.return_value = fake_now
            with self.assertLogs(logger, level="ERROR"):
                await run_usecase(
                    usecase="test_case_set_reviews",
                    usecase_service=self.mock_reviewer,
                    context=self.context,
                    conn=self.mock_tb_connection,
                    llm_factory=self.mock_llm_factory,
                    items=self.items,
                )

        current_time = fake_now.strftime("%Y-%m-%d %H:%M:%S")
        for tcs in self.test_case_sets:
            review_failed = get_translation("review_failed", self.context.language)
            error_message = get_translation("error_message", self.context.language)
            previous_comment = strip_html_body_tags(tcs.details.spec.reviewComment)
            failed_payload = SpecificationDetailsForUpdate(
                locker=OptionalUser(optional=None),
                reviewer=OptionalUser(optional=self.user_key),
                reviewComment=RichTextInfo(
                    html=(
                        f"<html><body><b>{review_failed} - {current_time}</b>"
                        f"<br/>{error_message}<br/><br/>{previous_comment}</body></html>"
                    ),
                    images=[],
                ),
            ).model_dump(exclude_unset=True)
            self.mock_tb_connection.session.patch.assert_any_call(
                f"{self.patch_url_prefix}{tcs.details.spec.key}", json=failed_payload
            )

        # Restore for tearDown
        self.mock_tb_connection.session.patch.side_effect = None

    async def test_reviewer_failure_is_logged_as_error(self):
        """When the AI reviewer raises, run_usecase logs the error and patches failure."""
        self.mock_reviewer._get_ai_response = AsyncMock(side_effect=Exception("service error"))

        fake_now = datetime.datetime(2025, 1, 1, 12, 0, 0, tzinfo=datetime.timezone.utc)
        with patch(
            "testbench_ai_service.usecases.test_case_set_reviews.utils.datetime"
        ) as mock_datetime:
            mock_datetime.now.return_value = fake_now
            with self.assertLogs(logger, level="ERROR"):
                await run_usecase(
                    usecase="test_case_set_reviews",
                    usecase_service=self.mock_reviewer,
                    context=self.context,
                    conn=self.mock_tb_connection,
                    llm_factory=self.mock_llm_factory,
                    items=self.items,
                )

        current_time = fake_now.strftime("%Y-%m-%d %H:%M:%S")
        for tcs in self.test_case_sets:
            review_failed = get_translation("review_failed", self.context.language)
            error_message = get_translation("error_message", self.context.language)
            previous_comment = strip_html_body_tags(tcs.details.spec.reviewComment)
            failed_payload = SpecificationDetailsForUpdate(
                locker=OptionalUser(optional=None),
                reviewer=OptionalUser(optional=self.user_key),
                reviewComment=RichTextInfo(
                    html=(
                        f"<html><body><b>{review_failed} - {current_time}</b>"
                        f"<br/>{error_message}<br/><br/>{previous_comment}</body></html>"
                    ),
                    images=[],
                ),
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
    ):
        tcs_str = prompt_config.placeholder_data.get("test_case", "")
        for uid, s in self.tcs_strings.items():
            if tcs_str == s:
                return self.review_responses[uid]
        return None


if __name__ == "__main__":
    unittest.main()
