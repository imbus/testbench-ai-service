import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import requests

from testbench_ai_service.agents.defect_explainer.agent import DefectExplainer
from testbench_ai_service.auth import AuthInfo, AuthType
from testbench_ai_service.config import LLMConfig, PromptConfig
from testbench_ai_service.llm.base import LLMProvider
from testbench_ai_service.models.agent import AgentResult, ExecutionContext
from testbench_ai_service.models.language import LanguageOption
from testbench_ai_service.models.testbench import (
    ActivityStatus,
    ExecStatus,
    ProjectRole,
    TestCaseBaseInformation,
    TestCaseExecution,
    TestCaseNode,
    VerdictStatus,
)
from testbench_ai_service.utils.i18n import load_translations


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


def _make_auth_info(auth_type=AuthType.SESSION_TOKEN, token="tok", user_key="U1"):
    return AuthInfo(auth_type=auth_type, token=token, user_key=user_key)


def _make_tc_node(uid="iTB-TC-1"):
    node = MagicMock()
    node.base.uniqueID = uid
    return node


def _make_tree(
    uid="iTB-TC-1",
    verdict=VerdictStatus.ToVerify,
    status=ActivityStatus.Performed,
    exec_is_none=False,
):
    exec_ = (
        None
        if exec_is_none
        else TestCaseExecution(
            key="E1",
            status=status,
            execStatus=ExecStatus.NotBlocked,
            verdict=verdict,
        )
    )
    root = TestCaseNode(
        base=TestCaseBaseInformation(
            numbering="1",
            parentKey="P1",
            name="TC 1",
            uniqueID=uid,
            matchesFilter=True,
        ),
        exec=exec_,
    )
    tree = MagicMock()
    tree.root = root
    return tree


def _make_tree_with_non_tc_root():
    """Return a mock tree whose root is not a TestCaseNode."""
    tree = MagicMock()
    tree.root = None
    return tree


def _make_tcs(uid="TCS1", key="K1", spec_key="SK1", exec_key="EK1"):
    tcs = MagicMock()
    tcs.details.uniqueID = uid
    tcs.details.key = key
    tcs.details.spec.key = spec_key
    tcs.details.exec.key = exec_key
    tcs.details.exec.comments = "<html><body></body></html>"
    return tcs


_AGENT_MODULE = "testbench_ai_service.agents.defect_explainer.agent"
_SUFFICIENT_ROLES = [ProjectRole.Tester]


class TestDefectExplainerPrecheck(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        load_translations()
        self.service = DefectExplainer()
        self.auth_info = _make_auth_info()

    async def test_returns_failed_when_no_nodes_found(self):
        context = _make_context()
        conn = MagicMock()

        with patch(f"{_AGENT_MODULE}.get_test_case_nodes", return_value=[]):
            result = await self.service.precheck(context, conn, self.auth_info)

        self.assertFalse(result.passed)
        self.assertIsNone(result.items)

    async def test_valid_node_passes_and_uid_is_included(self):
        context = _make_context()
        conn = MagicMock()
        node = _make_tc_node("iTB-TC-1")
        tree = _make_tree("iTB-TC-1")

        with (
            patch(f"{_AGENT_MODULE}.get_test_case_nodes", return_value=[node]),
            patch(f"{_AGENT_MODULE}.fetch_test_structure_tree", return_value=tree),
            patch(f"{_AGENT_MODULE}.is_test_case_locked_by_user", return_value=False),
            patch(f"{_AGENT_MODULE}.get_project_roles", return_value=_SUFFICIENT_ROLES),
        ):
            result = await self.service.precheck(context, conn, self.auth_info)

        self.assertTrue(result.passed)
        self.assertIn("iTB-TC-1", result.items)

    async def test_root_is_not_test_case_node_adds_warning_and_excludes(self):
        context = _make_context()
        conn = MagicMock()
        node = _make_tc_node("iTB-TC-1")
        tree = _make_tree_with_non_tc_root()

        with (
            patch(f"{_AGENT_MODULE}.get_test_case_nodes", return_value=[node]),
            patch(f"{_AGENT_MODULE}.fetch_test_structure_tree", return_value=tree),
            patch(f"{_AGENT_MODULE}.get_project_roles", return_value=_SUFFICIENT_ROLES),
        ):
            result = await self.service.precheck(context, conn, self.auth_info)

        self.assertFalse(result.passed)
        self.assertEqual(len(result.warnings), 1)
        self.assertIn("no execution data", result.warnings[0])

    async def test_root_exec_is_none_adds_warning_and_excludes(self):
        context = _make_context()
        conn = MagicMock()
        node = _make_tc_node("iTB-TC-1")
        tree = _make_tree("iTB-TC-1", exec_is_none=True)

        with (
            patch(f"{_AGENT_MODULE}.get_test_case_nodes", return_value=[node]),
            patch(f"{_AGENT_MODULE}.fetch_test_structure_tree", return_value=tree),
            patch(f"{_AGENT_MODULE}.get_project_roles", return_value=_SUFFICIENT_ROLES),
        ):
            result = await self.service.precheck(context, conn, self.auth_info)

        self.assertFalse(result.passed)
        self.assertEqual(len(result.warnings), 1)
        self.assertIn("no execution data", result.warnings[0])

    async def test_verdict_not_to_verify_adds_warning_and_excludes(self):
        context = _make_context()
        conn = MagicMock()
        node = _make_tc_node("iTB-TC-1")
        tree = _make_tree("iTB-TC-1", verdict=VerdictStatus.Fail)

        with (
            patch(f"{_AGENT_MODULE}.get_test_case_nodes", return_value=[node]),
            patch(f"{_AGENT_MODULE}.fetch_test_structure_tree", return_value=tree),
            patch(f"{_AGENT_MODULE}.get_project_roles", return_value=_SUFFICIENT_ROLES),
        ):
            result = await self.service.precheck(context, conn, self.auth_info)

        self.assertFalse(result.passed)
        self.assertEqual(len(result.warnings), 1)
        self.assertIn("To Verify", result.warnings[0])

    async def test_status_not_performed_adds_warning_and_excludes(self):
        context = _make_context()
        conn = MagicMock()
        node = _make_tc_node("iTB-TC-1")
        tree = _make_tree("iTB-TC-1", status=ActivityStatus.Running)

        with (
            patch(f"{_AGENT_MODULE}.get_test_case_nodes", return_value=[node]),
            patch(f"{_AGENT_MODULE}.fetch_test_structure_tree", return_value=tree),
            patch(f"{_AGENT_MODULE}.get_project_roles", return_value=_SUFFICIENT_ROLES),
        ):
            result = await self.service.precheck(context, conn, self.auth_info)

        self.assertFalse(result.passed)
        self.assertEqual(len(result.warnings), 1)
        self.assertIn("Performed", result.warnings[0])

    async def test_locked_node_adds_warning_and_is_excluded(self):
        context = _make_context()
        conn = MagicMock()
        node = _make_tc_node("iTB-TC-1")
        tree = _make_tree("iTB-TC-1")

        with (
            patch(f"{_AGENT_MODULE}.get_test_case_nodes", return_value=[node]),
            patch(f"{_AGENT_MODULE}.fetch_test_structure_tree", return_value=tree),
            patch(f"{_AGENT_MODULE}.is_test_case_locked_by_user", return_value=True),
            patch(f"{_AGENT_MODULE}.get_project_roles", return_value=_SUFFICIENT_ROLES),
        ):
            result = await self.service.precheck(context, conn, self.auth_info)

        self.assertFalse(result.passed)
        self.assertFalse(result.items)
        self.assertEqual(len(result.warnings), 1)
        self.assertIn("locked", result.warnings[0])


class TestDefectExplainerRun(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.service = DefectExplainer()

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
                self.service, "_generate_defect_explanations", new_callable=AsyncMock
            ) as mock_generate,
        ):
            await self.service.run(context, conn, llm_client, ["TCS1", "TCS2"])

        self.assertEqual(mock_generate.await_count, 2)

    async def test_run_with_none_items_is_noop(self):
        context = _make_context()
        conn = MagicMock()
        llm_client = MagicMock()

        with patch.object(
            self.service, "_generate_defect_explanations", new_callable=AsyncMock
        ) as mock_generate:
            await self.service.run(context, conn, llm_client, None)

        mock_generate.assert_not_awaited()

    async def test_run_with_empty_items_is_noop(self):
        context = _make_context()
        conn = MagicMock()
        llm_client = MagicMock()

        with patch.object(
            self.service, "_generate_defect_explanations", new_callable=AsyncMock
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


class TestBuildAgentData(unittest.TestCase):
    def setUp(self):
        self.service = DefectExplainer()

    def test_contains_failed_test_case_and_error_message(self):
        tcs = _make_tcs()
        error = {"error": "NullPointerException at line 42"}

        with patch(
            "testbench_ai_service.agents.defect_explainer.agent.get_test_case_set_as_string",
            return_value="test case text",
        ):
            data = self.service._build_agent_data(tcs, "TC1", error)

        self.assertIn("failed_test_case", data)
        self.assertIn("error_message", data)
        self.assertEqual(data["error_message"], "NullPointerException at line 42")


class TestGetAiResponse(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.service = DefectExplainer()

    async def test_wraps_llm_output_in_use_case_result(self):
        llm_client = MagicMock()
        llm_client.query_llm = AsyncMock(return_value="The defect is caused by X")
        llm_config = LLMConfig(provider=LLMProvider.OPENAI, model="gpt-4o")
        prompt_config = PromptConfig(file="prompts/test.yaml", name="Test")

        with patch("testbench_ai_service.agents.defect_explainer.agent.build_prompt") as mock_build:
            mock_prompt = MagicMock()
            mock_prompt.model_name = "gpt-4o"
            mock_prompt.messages = []
            mock_build.return_value = mock_prompt

            result = await self.service._get_ai_response(llm_client, llm_config, prompt_config)

        self.assertIsInstance(result, AgentResult)
        self.assertEqual(result.result, "The defect is caused by X")

    async def test_falls_back_to_prompt_model_when_config_model_is_none(self):
        llm_client = MagicMock()
        llm_client.query_llm = AsyncMock(return_value="explanation")
        llm_config = LLMConfig(provider=LLMProvider.OPENAI, model=None)
        prompt_config = PromptConfig(file="prompts/test.yaml", name="Test")

        with patch("testbench_ai_service.agents.defect_explainer.agent.build_prompt") as mock_build:
            mock_prompt = MagicMock()
            mock_prompt.model_name = "o1-from-prompt"
            mock_prompt.messages = []
            mock_build.return_value = mock_prompt

            await self.service._get_ai_response(llm_client, llm_config, prompt_config)

        call_kwargs = llm_client.query_llm.call_args
        used_model = call_kwargs.kwargs.get("model") or call_kwargs.args[0]
        self.assertEqual(used_model, "o1-from-prompt")


if __name__ == "__main__":
    unittest.main()
