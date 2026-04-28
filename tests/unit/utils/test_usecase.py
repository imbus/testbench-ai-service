from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException, status

from testbench_ai_service.config import LLMConfig, PromptConfig
from testbench_ai_service.llm.base import LLMProvider
from testbench_ai_service.models.testbench import FilteringOptions
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
    def __init__(self, project_key, tov_key, cycle_key, user_key, filtering=None):
        self.project_key = project_key
        self.tov_key = tov_key
        self.cycle_key = cycle_key
        self.user_key = user_key
        self.filtering = filtering


@pytest.fixture
def base_context():
    return _Context("proj1", "tov1", "cycle1", "user1")


@pytest.fixture
def base_request():
    req = MagicMock()
    req.project_key = "PROJ1"
    req.tov_key = "TOV1"
    req.cycle_key = "CYCLE1"
    req.root_uid = "ROOT1"
    req.language = None
    req.llm_config = None
    req.prompt_config = None
    req.filtering = None
    return req


@pytest.fixture
def resolved_mocks(mocker):
    """Patches all external collaborators used by build_execution_context."""
    return {
        "user_key": mocker.patch(
            "testbench_ai_service.utils.usecase.get_user_key", return_value="U1"
        ),
        "project_name": mocker.patch(
            "testbench_ai_service.utils.usecase.get_project_name", return_value="My Project"
        ),
        "language": mocker.patch(
            "testbench_ai_service.utils.usecase.get_language_from_config", return_value="en"
        ),
        "llm_config": mocker.patch(
            "testbench_ai_service.utils.usecase.get_llm_config",
            return_value=LLMConfig(provider=LLMProvider.OPENAI, model="gpt-4o"),
        ),
        "prompt_config": mocker.patch(
            "testbench_ai_service.utils.usecase.get_prompt_config",
            return_value=PromptConfig(file="prompts/test.yaml", name="test"),
        ),
    }


class TestCheckTestCaseSetIsLocked:
    def test_locked_by_another_user_returns_true(self, mocker, base_context):
        mocker.patch(
            "testbench_ai_service.utils.usecase.get_test_structure_tree",
            return_value=_Tree(_Root(_Tab(_Locker("other_user")), "tab")),
        )
        assert check_test_case_set_is_locked(MagicMock(), base_context, "uid1", "tab") is True

    def test_locked_by_same_user_returns_false(self, mocker, base_context):
        mocker.patch(
            "testbench_ai_service.utils.usecase.get_test_structure_tree",
            return_value=_Tree(_Root(_Tab(_Locker("user1")), "tab")),
        )
        assert check_test_case_set_is_locked(MagicMock(), base_context, "uid1", "tab") is False

    def test_unlocked_tab_returns_false(self, mocker, base_context):
        mocker.patch(
            "testbench_ai_service.utils.usecase.get_test_structure_tree",
            return_value=_Tree(_Root(_Tab(locker=None), "tab")),
        )
        assert check_test_case_set_is_locked(MagicMock(), base_context, "uid1", "tab") is False

    def test_nonexistent_tab_attribute_returns_false(self, mocker, base_context):
        mocker.patch(
            "testbench_ai_service.utils.usecase.get_test_structure_tree",
            return_value=_Tree(_Root(_Tab(), "tab")),
        )
        assert (
            check_test_case_set_is_locked(MagicMock(), base_context, "uid1", "nonexistent_tab")
            is False
        )


class TestBuildExecutionContext:
    def test_builds_context_with_resolved_fields(self, resolved_mocks, base_request):
        ctx = build_execution_context(
            "test_case_set_reviews", base_request, MagicMock(), MagicMock()
        )

        assert ctx.user_key == "U1"
        assert ctx.project_name == "My Project"
        assert ctx.project_key == "PROJ1"
        assert ctx.tov_key == "TOV1"
        assert ctx.cycle_key == "CYCLE1"
        assert ctx.language == "en"

    def test_request_language_overrides_config_language(self, resolved_mocks, base_request):
        base_request.language = "de"
        ctx = build_execution_context("uc", base_request, MagicMock(), MagicMock())

        resolved_mocks["language"].assert_not_called()
        assert ctx.language == "de"

    def test_filtering_is_forwarded_to_context(self, resolved_mocks, base_request):
        filtering = FilteringOptions(appliedFilters=None)
        base_request.filtering = filtering
        ctx = build_execution_context("uc", base_request, MagicMock(), MagicMock())

        assert ctx.filtering is filtering

    def test_unknown_project_raises_http_404(self, mocker, base_request):
        mocker.patch("testbench_ai_service.utils.usecase.get_user_key", return_value="U1")
        mocker.patch(
            "testbench_ai_service.utils.usecase.get_project_name",
            side_effect=ValueError("Project not found"),
        )

        with pytest.raises(HTTPException) as exc_info:
            build_execution_context("uc", base_request, MagicMock(), MagicMock())

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
