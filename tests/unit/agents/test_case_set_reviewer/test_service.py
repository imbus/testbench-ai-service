from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import requests

from testbench_ai_service.agents.test_case_set_reviewer.agent import TestCaseSetReviewer
from testbench_ai_service.auth import AuthInfo, AuthType
from testbench_ai_service.config import LLMConfig, PromptConfig
from testbench_ai_service.llm.base import LLMProvider
from testbench_ai_service.models.agent import AgentResult, ExecutionContext
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
    node.spec = None
    return node


def _make_tcs(uid="TCS1", key="K1", spec_key="SK1"):
    tcs = MagicMock()
    tcs.details.uniqueID = uid
    tcs.details.key = key
    tcs.details.spec.key = spec_key
    tcs.details.spec.description = None
    return tcs


_AGENT_MODULE = "testbench_ai_service.agents.test_case_set_reviewer.agent"
_SUFFICIENT_ROLES = [ProjectRole.TestManager]


class TestTestCaseSetReviewerPrecheck:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.service = TestCaseSetReviewer()
        self.auth_info = _make_auth_info()

    async def test_returns_passed_true_for_unlocked_tcs(self):
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
        assert result.warnings == []

    async def test_locked_tcs_adds_warning_and_is_excluded(self):
        context = _make_context()
        conn = MagicMock()
        node = _make_node("TCS-1", "K1")
        node.spec = MagicMock()
        node.spec.locker = MagicMock()
        node.spec.locker.key = "OTHER_USER"  # != context.user_key ("U1")

        with (
            patch(f"{_AGENT_MODULE}.get_test_case_set_nodes", return_value=[node]),
            # Use a non-privileged writing role: Tester is blocked by locks
            patch(f"{_AGENT_MODULE}.get_project_roles", return_value=[ProjectRole.Tester]),
        ):
            result = await self.service.precheck(context, conn, self.auth_info)

        assert not (result.passed)
        assert not (result.items)
        assert len(result.warnings) == 1

    async def test_empty_nodes_returns_passed_false(self):
        context = _make_context()
        conn = MagicMock()

        with (
            patch(f"{_AGENT_MODULE}.get_test_case_set_nodes", return_value=[]),
            patch(f"{_AGENT_MODULE}.get_project_roles", return_value=_SUFFICIENT_ROLES),
        ):
            result = await self.service.precheck(context, conn, self.auth_info)

        assert not (result.passed)
        assert result.items == []


class TestTestCaseSetReviewerRun:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.service = TestCaseSetReviewer()

    async def test_run_invokes_review_for_matched_items(self):
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
                self.service, "_review_test_case_set", new_callable=AsyncMock
            ) as mock_review,
        ):
            await self.service.run(context, conn, llm_client, ["TCS1", "TCS2"])

        assert mock_review.await_count == 2

    async def test_run_with_none_items_is_noop(self):
        context = _make_context()
        conn = MagicMock()
        llm_client = MagicMock()

        with patch.object(
            self.service, "_review_test_case_set", new_callable=AsyncMock
        ) as mock_review:
            await self.service.run(context, conn, llm_client, None)

        mock_review.assert_not_awaited()

    async def test_run_with_empty_items_is_noop(self):
        context = _make_context()
        conn = MagicMock()
        llm_client = MagicMock()

        with patch.object(
            self.service, "_review_test_case_set", new_callable=AsyncMock
        ) as mock_review:
            await self.service.run(context, conn, llm_client, [])

        mock_review.assert_not_awaited()

    async def test_http_error_from_catalog_is_handled(self):
        context = _make_context()
        conn = MagicMock()
        llm_client = MagicMock()

        with (
            patch(
                f"{_AGENT_MODULE}.get_test_case_set_catalog",
                side_effect=requests.exceptions.HTTPError("404"),
            ),
            patch(f"{_AGENT_MODULE}.handle_requests_http_error") as mock_handler,
        ):
            await self.service.run(context, conn, llm_client, ["TCS1"])

        mock_handler.assert_called_once()


class TestBuildAgentData:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.service = TestCaseSetReviewer()

    def test_contains_required_keys(self):
        tcs = _make_tcs()

        with (
            patch(
                "testbench_ai_service.agents.test_case_set_reviewer.agent.get_test_case_set_as_string",
                return_value="test case string",
            ),
            patch(
                "testbench_ai_service.agents.test_case_set_reviewer.agent.get_parameter_combinations_as_string",
                return_value="| col | val |",
            ),
        ):
            data = self.service._build_agent_data(tcs)

        assert "test_case" in data
        assert "parameter_combinations" in data
        assert "test_case_set_obj" in data

    def test_description_included_when_present(self):
        tcs = _make_tcs()
        tcs.details.spec.description = "<html><body>Description</body></html>"

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
                "testbench_ai_service.agents.test_case_set_reviewer.agent.extract_text_from_html_body",
                return_value="Plain description",
            ),
        ):
            data = self.service._build_agent_data(tcs)

        assert "test_case_set_description" in data
        assert data["test_case_set_description"] == "Plain description"


class TestGetAiResponse:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.service = TestCaseSetReviewer()

    async def test_returns_use_case_result(self):
        llm_client = MagicMock()
        llm_client.query_llm = AsyncMock(return_value="- Review note")
        llm_config = LLMConfig(provider=LLMProvider.OPENAI, model="gpt-4o")
        prompt_config = PromptConfig(file="prompts/test.yaml")

        with patch(
            "testbench_ai_service.agents.test_case_set_reviewer.agent.build_prompt"
        ) as mock_build:
            mock_prompt = MagicMock()
            mock_prompt.model_name = "gpt-4o"
            mock_prompt.messages = []
            mock_build.return_value = mock_prompt

            result = await self.service._get_ai_response(llm_client, llm_config, prompt_config)

        assert isinstance(result, AgentResult)
        assert result.result == "- Review note"

    async def test_uses_prompt_model_when_llm_config_model_is_none(self):
        llm_client = MagicMock()
        llm_client.query_llm = AsyncMock(return_value="response")
        llm_config = LLMConfig(provider=LLMProvider.OPENAI, model=None)
        prompt_config = PromptConfig(file="prompts/test.yaml")

        with patch(
            "testbench_ai_service.agents.test_case_set_reviewer.agent.build_prompt"
        ) as mock_build:
            mock_prompt = MagicMock()
            mock_prompt.model_name = "gpt-4o-from-prompt"
            mock_prompt.messages = []
            mock_build.return_value = mock_prompt

            await self.service._get_ai_response(llm_client, llm_config, prompt_config)

        call_kwargs = llm_client.query_llm.call_args
        assert call_kwargs.kwargs.get("model") or call_kwargs.args[0] == "gpt-4o-from-prompt"
