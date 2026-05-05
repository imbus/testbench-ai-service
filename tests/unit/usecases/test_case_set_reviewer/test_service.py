import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import requests

from testbench_ai_service.agents.test_case_set_reviewer.agent import TestCaseSetReviewer
from testbench_ai_service.config import LLMConfig, PromptConfig
from testbench_ai_service.llm.base import LLMProvider
from testbench_ai_service.models.agent import AgentResult, ExecutionContext
from testbench_ai_service.models.language import LanguageOption


def _make_context(**overrides):
    defaults = {
        "user_key": "U1",
        "project_key": "P1",
        "project_name": "Project",
        "tov_key": "T1",
        "cycle_key": "C1",
        "root_uid": None,
        "language": LanguageOption.ENGLISH,
        "llm_config": LLMConfig(provider=LLMProvider.OPENAI, model="gpt-4o"),
        "prompt_config": PromptConfig(file="prompts/test.yaml", name="Test"),
    }
    defaults.update(overrides)
    return ExecutionContext(**defaults)


def _make_tcs(uid="TCS1", key="K1", spec_key="SK1"):
    tcs = MagicMock()
    tcs.details.uniqueID = uid
    tcs.details.key = key
    tcs.details.spec.key = spec_key
    tcs.details.spec.description = None
    return tcs


class TestTestCaseSetReviewerPrecheck(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.service = TestCaseSetReviewer()

    async def test_returns_passed_true_for_unlocked_tcs(self):
        context = _make_context()
        conn = MagicMock()
        tcs = _make_tcs()

        with (
            patch(
                "testbench_ai_service.agents.test_case_set_reviewer.agent.get_test_case_set_catalog",
                return_value={"TCS1": tcs},
            ),
            patch(
                "testbench_ai_service.agents.test_case_set_reviewer.agent.check_test_case_set_is_locked",
                return_value=False,
            ),
        ):
            result = await self.service.precheck(context, conn)

        self.assertTrue(result.passed)
        self.assertIn(tcs, result.items)
        self.assertEqual(result.warnings, [])

    async def test_locked_tcs_adds_warning_and_is_excluded(self):
        context = _make_context()
        conn = MagicMock()
        tcs = _make_tcs()

        with (
            patch(
                "testbench_ai_service.agents.test_case_set_reviewer.agent.get_test_case_set_catalog",
                return_value={"TCS1": tcs},
            ),
            patch(
                "testbench_ai_service.agents.test_case_set_reviewer.agent.check_test_case_set_is_locked",
                return_value=True,
            ),
        ):
            result = await self.service.precheck(context, conn)

        self.assertFalse(result.passed)
        self.assertEqual(result.items, [])
        self.assertEqual(len(result.warnings), 1)

    async def test_http_error_is_handled(self):
        context = _make_context()
        conn = MagicMock()

        with (
            patch(
                "testbench_ai_service.agents.test_case_set_reviewer.agent.get_test_case_set_catalog",
                side_effect=requests.exceptions.HTTPError("404"),
            ),
            patch(
                "testbench_ai_service.agents.test_case_set_reviewer.agent.handle_requests_http_error"
            ) as mock_handler,
        ):
            await self.service.precheck(context, conn)

        mock_handler.assert_called_once()

    async def test_empty_catalog_returns_passed_false(self):
        context = _make_context()
        conn = MagicMock()

        with patch(
            "testbench_ai_service.agents.test_case_set_reviewer.agent.get_test_case_set_catalog",
            return_value={},
        ):
            result = await self.service.precheck(context, conn)

        self.assertFalse(result.passed)
        self.assertEqual(result.items, [])


class TestTestCaseSetReviewerRun(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.service = TestCaseSetReviewer()

    async def test_run_invokes_review_for_all_items(self):
        context = _make_context()
        conn = MagicMock()
        llm_client = MagicMock()

        with patch.object(
            self.service, "_review_test_case_set", new_callable=AsyncMock
        ) as mock_review:
            await self.service.run(context, conn, llm_client)

        self.assertEqual(mock_review.await_count, 2)

    async def test_run_with_empty_items_is_noop(self):
        context = _make_context()
        conn = MagicMock()
        llm_client = MagicMock()

        with patch.object(
            self.service, "_review_test_case_set", new_callable=AsyncMock
        ) as mock_review:
            await self.service.run(context, conn, llm_client)

        mock_review.assert_not_awaited()


class TestBuildPlaceholderData(unittest.TestCase):
    def setUp(self):
        self.service = TestCaseSetReviewer()

    def test_contains_required_keys(self):
        tcs = _make_tcs()
        prompt_config = PromptConfig(file="prompts/test.yaml", name="Test")

        with (
            patch(
                "testbench_ai_service.agents.test_case_set_reviewer.agent.get_test_case_set_as_string",
                return_value="test case string",
            ),
            patch(
                "testbench_ai_service.agents.test_case_set_reviewer.agent.get_parameter_combinations_as_string",
                return_value="| col | val |",
            ),
            patch(
                "testbench_ai_service.agents.test_case_set_reviewer.agent.get_test_case_glossary",
                return_value="Glossary text",
            ),
        ):
            data = self.service._build_placeholder_data(tcs, prompt_config, LanguageOption.ENGLISH)

        self.assertIn("test_case", data)
        self.assertIn("parameter_combinations", data)
        self.assertIn("glossary", data)
        self.assertIn("test_case_set_obj", data)

    def test_description_included_when_present(self):
        tcs = _make_tcs()
        tcs.details.spec.description = "<html><body>Description</body></html>"
        prompt_config = PromptConfig(file="prompts/test.yaml", name="Test")

        with (
            patch(
                "testbench_ai_service.agents.test_case_set_reviewer.agent.get_test_case_set_as_string",
                return_value="",
            ),
            patch(
                "testbench_ai_service.agents.test_case_set_reviewer.agent.get_parameter_combinations_as_string",
                return_value="",
            ),
            patch(
                "testbench_ai_service.agents.test_case_set_reviewer.agent.get_test_case_glossary",
                return_value="",
            ),
            patch(
                "testbench_ai_service.agents.test_case_set_reviewer.agent.extract_text_from_html_body",
                return_value="Plain description",
            ),
        ):
            data = self.service._build_placeholder_data(tcs, prompt_config, LanguageOption.ENGLISH)

        self.assertIn("test_case_set_description", data)
        self.assertEqual(data["test_case_set_description"], "Plain description")


class TestGetAiResponse(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.service = TestCaseSetReviewer()

    async def test_returns_use_case_result(self):
        llm_client = MagicMock()
        llm_client.query_llm = AsyncMock(return_value="- Review note")
        llm_config = LLMConfig(provider=LLMProvider.OPENAI, model="gpt-4o")
        prompt_config = PromptConfig(file="prompts/test.yaml", name="Test")

        with patch(
            "testbench_ai_service.agents.test_case_set_reviewer.agent.build_prompt"
        ) as mock_build:
            mock_prompt = MagicMock()
            mock_prompt.model_name = "gpt-4o"
            mock_prompt.messages = []
            mock_build.return_value = mock_prompt

            result = await self.service._get_ai_response(llm_client, llm_config, prompt_config)

        self.assertIsInstance(result, AgentResult)
        self.assertEqual(result.result, "- Review note")

    async def test_uses_prompt_model_when_llm_config_model_is_none(self):
        llm_client = MagicMock()
        llm_client.query_llm = AsyncMock(return_value="response")
        llm_config = LLMConfig(provider=LLMProvider.OPENAI, model=None)
        prompt_config = PromptConfig(file="prompts/test.yaml", name="Test")

        with patch(
            "testbench_ai_service.agents.test_case_set_reviewer.agent.build_prompt"
        ) as mock_build:
            mock_prompt = MagicMock()
            mock_prompt.model_name = "gpt-4o-from-prompt"
            mock_prompt.messages = []
            mock_build.return_value = mock_prompt

            await self.service._get_ai_response(llm_client, llm_config, prompt_config)

        call_kwargs = llm_client.query_llm.call_args
        self.assertEqual(
            call_kwargs.kwargs.get("model") or call_kwargs.args[0], "gpt-4o-from-prompt"
        )


if __name__ == "__main__":
    unittest.main()
