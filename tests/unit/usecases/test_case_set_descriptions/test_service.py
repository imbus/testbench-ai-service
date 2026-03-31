import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import requests

from testbench_ai_service.config import LLMConfig, PromptConfig
from testbench_ai_service.llm.base import LLMProvider
from testbench_ai_service.models.language import LanguageOption
from testbench_ai_service.models.usecase import ExecutionContext, UseCaseResult
from testbench_ai_service.usecases.test_case_set_descriptions.service import TestCaseSetDescriber


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
    return tcs


class TestTestCaseSetDescriberPrecheck(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.service = TestCaseSetDescriber()

    async def test_unlocked_tcs_passes_and_is_included(self):
        context = _make_context()
        conn = MagicMock()
        tcs = _make_tcs()

        with (
            patch(
                "testbench_ai_service.usecases.test_case_set_descriptions.service.get_test_case_set_catalog",
                return_value={"TCS1": tcs},
            ),
            patch(
                "testbench_ai_service.usecases.test_case_set_descriptions.service.check_test_case_set_is_locked",
                return_value=False,
            ),
        ):
            result = await self.service.precheck(context, conn)

        self.assertTrue(result.passed)
        self.assertIn(tcs, result.items)

    async def test_locked_tcs_adds_warning_and_is_excluded(self):
        context = _make_context()
        conn = MagicMock()
        tcs = _make_tcs()

        with (
            patch(
                "testbench_ai_service.usecases.test_case_set_descriptions.service.get_test_case_set_catalog",
                return_value={"TCS1": tcs},
            ),
            patch(
                "testbench_ai_service.usecases.test_case_set_descriptions.service.check_test_case_set_is_locked",
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
                "testbench_ai_service.usecases.test_case_set_descriptions.service.get_test_case_set_catalog",
                side_effect=requests.exceptions.HTTPError("500"),
            ),
            patch(
                "testbench_ai_service.usecases.test_case_set_descriptions.service.handle_requests_http_error"
            ) as mock_handler,
        ):
            await self.service.precheck(context, conn)

        mock_handler.assert_called_once()

    async def test_empty_catalog_returns_passed_false(self):
        context = _make_context()
        conn = MagicMock()

        with patch(
            "testbench_ai_service.usecases.test_case_set_descriptions.service.get_test_case_set_catalog",
            return_value={},
        ):
            result = await self.service.precheck(context, conn)

        self.assertFalse(result.passed)


class TestTestCaseSetDescriberRun(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.service = TestCaseSetDescriber()

    async def test_run_invokes_generate_for_all_items(self):
        context = _make_context()
        conn = MagicMock()
        llm_client = MagicMock()
        items = [_make_tcs("TCS1"), _make_tcs("TCS2")]

        with patch.object(
            self.service, "_generate_test_case_set_description", new_callable=AsyncMock
        ) as mock_generate:
            await self.service.run(context, conn, llm_client, items)

        self.assertEqual(mock_generate.await_count, 2)

    async def test_run_with_empty_items_is_noop(self):
        context = _make_context()
        conn = MagicMock()
        llm_client = MagicMock()

        with patch.object(
            self.service, "_generate_test_case_set_description", new_callable=AsyncMock
        ) as mock_generate:
            await self.service.run(context, conn, llm_client, [])

        mock_generate.assert_not_awaited()


class TestBuildPlaceholderData(unittest.TestCase):
    def setUp(self):
        self.service = TestCaseSetDescriber()

    def test_contains_expected_keys(self):
        tcs = _make_tcs()

        with (
            patch(
                "testbench_ai_service.usecases.test_case_set_descriptions.service.get_test_case_set_as_string",
                return_value="steps",
            ),
            patch(
                "testbench_ai_service.usecases.test_case_set_descriptions.service.get_parameter_combinations_as_string",
                return_value="| col | val |",
            ),
        ):
            data = self.service._build_placeholder_data(tcs)

        self.assertIn("step_sequence", data)
        self.assertIn("parameter_combinations", data)
        self.assertIn("test_case_set_obj", data)
        self.assertIs(data["test_case_set_obj"], tcs)


class TestGetAiResponse(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.service = TestCaseSetDescriber()

    async def test_wraps_llm_output_in_use_case_result(self):
        llm_client = MagicMock()
        llm_client.query_llm = AsyncMock(return_value="Generated description")
        llm_config = LLMConfig(provider=LLMProvider.OPENAI, model="gpt-4o")
        prompt_config = PromptConfig(file="prompts/test.yaml", name="Test")

        with patch(
            "testbench_ai_service.usecases.test_case_set_descriptions.service.build_prompt"
        ) as mock_build:
            mock_prompt = MagicMock()
            mock_prompt.model_name = "gpt-4o"
            mock_prompt.messages = []
            mock_build.return_value = mock_prompt

            result = await self.service._get_ai_response(llm_client, llm_config, prompt_config)

        self.assertIsInstance(result, UseCaseResult)
        self.assertEqual(result.result, "Generated description")

    async def test_falls_back_to_prompt_model_when_config_model_is_none(self):
        llm_client = MagicMock()
        llm_client.query_llm = AsyncMock(return_value="desc")
        llm_config = LLMConfig(provider=LLMProvider.OPENAI, model=None)
        prompt_config = PromptConfig(file="prompts/test.yaml", name="Test")

        with patch(
            "testbench_ai_service.usecases.test_case_set_descriptions.service.build_prompt"
        ) as mock_build:
            mock_prompt = MagicMock()
            mock_prompt.model_name = "fallback-model"
            mock_prompt.messages = []
            mock_build.return_value = mock_prompt

            await self.service._get_ai_response(llm_client, llm_config, prompt_config)

        call_kwargs = llm_client.query_llm.call_args
        used_model = call_kwargs.kwargs.get("model") or call_kwargs.args[0]
        self.assertEqual(used_model, "fallback-model")


if __name__ == "__main__":
    unittest.main()
