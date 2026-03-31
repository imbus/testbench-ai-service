import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from testbench_ai_service.config import LLMConfig, PromptConfig
from testbench_ai_service.llm.base import LLMProvider
from testbench_ai_service.utils.usecase import (
    build_execution_context,
    check_test_case_set_is_locked,
)


class _Locker:
    def __init__(self, key: str):
        self.key = key


class _Tab:
    def __init__(self, locker=None):
        self.locker = locker


class _Root:
    def __init__(self, tab=None, tab_name="tab"):
        setattr(self, tab_name, tab)


class _Tree:
    def __init__(self, root):
        self.root = root


class _Context:
    def __init__(self, project_key, tov_key, cycle_key, user_key):
        self.project_key = project_key
        self.tov_key = tov_key
        self.cycle_key = cycle_key
        self.user_key = user_key


class TestCheckTestCaseSetIsLocked(unittest.TestCase):
    """check_test_case_set_is_locked returns True only when locked by a *different* user."""

    @patch("testbench_ai_service.utils.usecase.get_test_structure_tree")
    def test_locked_by_another_user_returns_true(self, mock_get_tree):
        mock_get_tree.return_value = _Tree(_Root(_Tab(_Locker("other_user")), "tab"))
        result = check_test_case_set_is_locked(
            MagicMock(), _Context("proj1", "tov1", "cycle1", "user1"), "uid1", "tab"
        )
        self.assertTrue(result)

    @patch("testbench_ai_service.utils.usecase.get_test_structure_tree")
    def test_locked_by_same_user_returns_false(self, mock_get_tree):
        mock_get_tree.return_value = _Tree(_Root(_Tab(_Locker("user1")), "tab"))
        result = check_test_case_set_is_locked(
            MagicMock(), _Context("proj1", "tov1", "cycle1", "user1"), "uid1", "tab"
        )
        self.assertFalse(result)

    @patch("testbench_ai_service.utils.usecase.get_test_structure_tree")
    def test_unlocked_tab_returns_false(self, mock_get_tree):
        mock_get_tree.return_value = _Tree(_Root(_Tab(locker=None), "tab"))
        result = check_test_case_set_is_locked(
            MagicMock(), _Context("proj1", "tov1", "cycle1", "user1"), "uid1", "tab"
        )
        self.assertFalse(result)

    @patch("testbench_ai_service.utils.usecase.get_test_structure_tree")
    def test_nonexistent_tab_attribute_returns_false(self, mock_get_tree):
        mock_get_tree.return_value = _Tree(_Root(_Tab(), "tab"))
        result = check_test_case_set_is_locked(
            MagicMock(), _Context("proj1", "tov1", "cycle1", "user1"), "uid1", "nonexistent_tab"
        )
        self.assertFalse(result)


class TestBuildExecutionContext(unittest.TestCase):
    """build_execution_context assembles a fully resolved ExecutionContext."""

    def _make_request(self, **kwargs):
        req = MagicMock()
        req.project_key = kwargs.get("project_key", "PROJ1")
        req.tov_key = kwargs.get("tov_key", "TOV1")
        req.cycle_key = kwargs.get("cycle_key", "CYCLE1")
        req.root_uid = kwargs.get("root_uid", "ROOT1")
        req.language = kwargs.get("language")
        req.llm_config = kwargs.get("llm_config")
        req.prompt_config = kwargs.get("prompt_config")
        return req

    @patch("testbench_ai_service.utils.usecase.get_prompt_config")
    @patch("testbench_ai_service.utils.usecase.get_llm_config")
    @patch("testbench_ai_service.utils.usecase.get_language_from_config")
    @patch("testbench_ai_service.utils.usecase.get_project_name")
    @patch("testbench_ai_service.utils.usecase.get_user_key")
    def test_builds_context_with_resolved_fields(
        self,
        mock_user_key,
        mock_project_name,
        mock_language,
        mock_llm_config,
        mock_prompt_config,
    ):
        mock_user_key.return_value = "U1"
        mock_project_name.return_value = "My Project"
        mock_language.return_value = "en"
        mock_llm_config.return_value = LLMConfig(provider=LLMProvider.OPENAI, model="gpt-4o")
        mock_prompt_config.return_value = PromptConfig(file="prompts/test.yaml", name="test")

        conn = MagicMock()
        app_config = MagicMock()
        request = self._make_request()
        ctx = build_execution_context("test_case_set_reviews", request, conn, app_config)

        self.assertEqual(ctx.user_key, "U1")
        self.assertEqual(ctx.project_name, "My Project")
        self.assertEqual(ctx.project_key, "PROJ1")
        self.assertEqual(ctx.tov_key, "TOV1")
        self.assertEqual(ctx.cycle_key, "CYCLE1")
        self.assertEqual(ctx.language, "en")

    @patch("testbench_ai_service.utils.usecase.get_prompt_config")
    @patch("testbench_ai_service.utils.usecase.get_llm_config")
    @patch("testbench_ai_service.utils.usecase.get_language_from_config")
    @patch("testbench_ai_service.utils.usecase.get_project_name")
    @patch("testbench_ai_service.utils.usecase.get_user_key")
    def test_request_language_overrides_config_language(
        self,
        mock_user_key,
        mock_project_name,
        mock_language,
        mock_llm_config,
        mock_prompt_config,
    ):
        mock_user_key.return_value = "U1"
        mock_project_name.return_value = "Proj"
        mock_llm_config.return_value = LLMConfig(provider=LLMProvider.OPENAI, model="gpt-4o")
        mock_prompt_config.return_value = PromptConfig(file="prompts/test.yaml", name="test")

        request = self._make_request(language="de")
        ctx = build_execution_context("uc", request, MagicMock(), MagicMock())

        # Config language resolver should NOT be called when request provides a language
        mock_language.assert_not_called()
        self.assertEqual(ctx.language, "de")

    @patch("testbench_ai_service.utils.usecase.get_project_name")
    @patch("testbench_ai_service.utils.usecase.get_user_key")
    def test_unknown_project_raises_http_404(self, mock_user_key, mock_project_name):
        mock_user_key.return_value = "U1"
        mock_project_name.side_effect = ValueError("Project not found")

        with self.assertRaises(HTTPException) as ctx:
            build_execution_context("uc", self._make_request(), MagicMock(), MagicMock())

        self.assertEqual(ctx.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
