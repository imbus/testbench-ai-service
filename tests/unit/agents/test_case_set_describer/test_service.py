from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import requests

from testbench_ai_service.agents.test_case_set_describer.agent import TestCaseSetDescriber
from testbench_ai_service.auth import AuthInfo, AuthType
from testbench_ai_service.llm.base import LLMProvider
from testbench_ai_service.models.agent import AgentResult, ExecutionContext
from testbench_ai_service.models.config import LLMConfig, PromptConfig
from testbench_ai_service.models.language import LanguageOption
from testbench_ai_service.models.testbench import ProjectRole


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
        "prompt_config": PromptConfig(file="prompts/test.yaml"),
    }
    defaults.update(overrides)
    return ExecutionContext(**defaults)


def _make_auth_info(auth_type=AuthType.SESSION_TOKEN, token="tok", user_key="U1"):
    return AuthInfo(auth_type=auth_type, token=token, user_key=user_key, conn=MagicMock())


def _make_node(uid="TCS-1", key="K1"):
    node = MagicMock()
    node.base.uniqueID = uid
    node.base.key = key
    node.spec = None  # no lock info; set node.spec.locker explicitly for locked-node tests
    return node


def _make_tcs(uid="TCS1", key="K1", spec_key="SK1"):
    tcs = MagicMock()
    tcs.details.uniqueID = uid
    tcs.details.key = key
    tcs.details.spec.key = spec_key
    return tcs


_AGENT_MODULE = "testbench_ai_service.agents.test_case_set_describer.agent"
_SUFFICIENT_ROLES = [ProjectRole.TestManager]


class TestTestCaseSetDescriberPrecheck:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.service = TestCaseSetDescriber()
        self.auth_info = _make_auth_info()

    async def test_unlocked_tcs_passes_and_uid_is_included(self):
        context = _make_context()
        conn = MagicMock()
        node = _make_node("TCS-1", "K1")  # node.spec = None → not locked

        with (
            patch(f"{_AGENT_MODULE}.get_test_case_set_nodes", return_value=[node]),
            patch(f"{_AGENT_MODULE}.get_project_roles", return_value=_SUFFICIENT_ROLES),
        ):
            result = await self.service.precheck(context, conn, self.auth_info)

        assert result.passed
        assert "TCS-1" in result.items

    async def test_locked_tcs_adds_warning_and_is_excluded(self):
        context = _make_context()
        conn = MagicMock()
        node = _make_node("TCS-1", "K1")
        node.spec = MagicMock()
        node.spec.locker = MagicMock()
        node.spec.locker.key = "OTHER_USER"  # != context.user_key ("U1")

        with (
            patch(f"{_AGENT_MODULE}.get_test_case_set_nodes", return_value=[node]),
            # TestDesigner is a writing role but not privileged, so lock checks apply
            patch(f"{_AGENT_MODULE}.get_project_roles", return_value=[ProjectRole.TestDesigner]),
        ):
            result = await self.service.precheck(context, conn, self.auth_info)

        assert not (result.passed)
        assert not (result.items)
        assert len(result.warnings) == 1

    async def test_empty_nodes_returns_passed_false(self):
        context = _make_context()
        conn = MagicMock()

        with (
            patch(f"{_AGENT_MODULE}.get_project_roles", return_value=_SUFFICIENT_ROLES),
            patch(f"{_AGENT_MODULE}.get_test_case_set_nodes", return_value=[]),
        ):
            result = await self.service.precheck(context, conn, self.auth_info)

        assert not (result.passed)


class TestTestCaseSetDescriberRun:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.service = TestCaseSetDescriber()

    async def test_run_invokes_generate_for_matched_items(self):
        context = _make_context()
        conn = MagicMock()
        llm_client = MagicMock()
        tcs1 = _make_tcs(uid="TCS1")
        tcs2 = _make_tcs(uid="TCS2")

        with (
            patch(
                f"{_AGENT_MODULE}.get_test_case_set_catalog",
                return_value={"TCS1": tcs1, "TCS2": tcs2},
            ),
            patch.object(
                self.service, "_generate_test_case_set_description", new_callable=AsyncMock
            ) as mock_generate,
        ):
            await self.service.run(context, conn, llm_client, ["TCS1", "TCS2"])

        assert mock_generate.await_count == 2

    async def test_run_with_none_items_is_noop(self):
        context = _make_context()
        conn = MagicMock()
        llm_client = MagicMock()

        with patch.object(
            self.service, "_generate_test_case_set_description", new_callable=AsyncMock
        ) as mock_generate:
            await self.service.run(context, conn, llm_client, None)

        mock_generate.assert_not_awaited()

    async def test_run_with_empty_items_is_noop(self):
        context = _make_context()
        conn = MagicMock()
        llm_client = MagicMock()

        with patch.object(
            self.service, "_generate_test_case_set_description", new_callable=AsyncMock
        ) as mock_generate:
            await self.service.run(context, conn, llm_client, [])

        mock_generate.assert_not_awaited()

    async def test_http_error_from_catalog_is_handled(self):
        context = _make_context()
        conn = MagicMock()
        llm_client = MagicMock()

        with (
            patch(
                f"{_AGENT_MODULE}.get_test_case_set_catalog",
                side_effect=requests.exceptions.HTTPError("500"),
            ),
            patch(f"{_AGENT_MODULE}.handle_requests_http_error") as mock_handler,
        ):
            await self.service.run(context, conn, llm_client, ["TCS1"])

        mock_handler.assert_called_once()


class TestBuildAgentData:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.service = TestCaseSetDescriber()

    def test_contains_expected_keys(self):
        tcs = _make_tcs()

        with (
            patch(
                "testbench_ai_service.agents.test_case_set_describer.agent.test_case_set_as_str",
                return_value="steps",
            ),
            patch(
                "testbench_ai_service.agents.test_case_set_describer.agent.parameter_combinations_as_str",
                return_value="| col | val |",
            ),
        ):
            data = self.service._build_agent_data(tcs)

        assert "test_case_set" in data
        assert "parameter_combinations" in data
        assert "test_case_set_obj" in data
        assert data["test_case_set_obj"] is tcs


class TestGetAiResponse:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.service = TestCaseSetDescriber()

    async def test_wraps_llm_output_in_use_case_result(self):
        llm_client = MagicMock()
        llm_client.query_llm = AsyncMock(return_value="Generated description")
        llm_config = LLMConfig(provider=LLMProvider.OPENAI, model="gpt-4o")
        prompt_config = PromptConfig(file="prompts/test.yaml")

        with patch(
            "testbench_ai_service.agents.test_case_set_describer.agent.build_prompt"
        ) as mock_build:
            mock_prompt = MagicMock()
            mock_prompt.model_name = "gpt-4o"
            mock_prompt.messages = []
            mock_build.return_value = mock_prompt

            result = await self.service._get_ai_response(llm_client, llm_config, prompt_config)

        assert isinstance(result, AgentResult)
        assert result.result == "Generated description"

    async def test_falls_back_to_prompt_model_when_config_model_is_none(self):
        llm_client = MagicMock()
        llm_client.query_llm = AsyncMock(return_value="desc")
        llm_config = LLMConfig(provider=LLMProvider.OPENAI, model=None)
        prompt_config = PromptConfig(file="prompts/test.yaml")

        with patch(
            "testbench_ai_service.agents.test_case_set_describer.agent.build_prompt"
        ) as mock_build:
            mock_prompt = MagicMock()
            mock_prompt.model_name = "fallback-model"
            mock_prompt.messages = []
            mock_build.return_value = mock_prompt

            await self.service._get_ai_response(llm_client, llm_config, prompt_config)

        call_kwargs = llm_client.query_llm.call_args
        used_model = call_kwargs.kwargs.get("model") or call_kwargs.args[0]
        assert used_model == "fallback-model"
