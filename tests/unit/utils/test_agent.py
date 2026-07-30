from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException, status

from testbench_ai_service.auth import AuthInfo, AuthType
from testbench_ai_service.llm.base import LLMProvider
from testbench_ai_service.models.config import LLMConfig, PromptConfig
from testbench_ai_service.models.language import LanguageOption
from testbench_ai_service.models.testbench import FilteringOptions
from testbench_ai_service.utils.agent import MIN_TESTBENCH_VERSION, build_execution_context, check_min_testbench_version
from testbench_ai_service.utils.i18n import load_translations


def _session_auth(user_key: str = "U1") -> AuthInfo:
    return AuthInfo(
        auth_type=AuthType.SESSION_TOKEN, token="tok", user_key=user_key, conn=MagicMock()
    )


def _jwt_auth(token: str, user_key: str = "U1") -> AuthInfo:
    return AuthInfo(auth_type=AuthType.JWT_TOKEN, token=token, user_key=user_key, conn=MagicMock())


@pytest.fixture
def base_request():
    req = MagicMock()
    req.project_key = "PROJ1"
    req.tov_key = "TOV1"
    req.cycle_key = "CYCLE1"
    req.root_uid = "ROOT1"
    req.root_key = None
    req.element_type = None
    req.tree_type = None
    req.language = None
    req.llm_config = None
    req.prompt_config = None
    req.filtering = None
    return req


@pytest.fixture
def resolved_mocks(mocker):
    """Patches all external collaborators used by build_execution_context."""
    return {
        "project_name": mocker.patch(
            "testbench_ai_service.utils.agent.get_project_name", return_value="My Project"
        ),
        "language": mocker.patch(
            "testbench_ai_service.utils.agent.get_language_from_config", return_value="en"
        ),
        "llm_config": mocker.patch(
            "testbench_ai_service.utils.agent.get_llm_config",
            return_value=LLMConfig(provider=LLMProvider.OPENAI, model="gpt-4o"),
        ),
        "prompt_config": mocker.patch(
            "testbench_ai_service.utils.agent.get_prompt_config",
            return_value=PromptConfig(file="prompts/test.yaml", name="test"),
        ),
    }


class TestBuildExecutionContextSessionToken:
    """Session-token path of build_execution_context."""

    def test_builds_context_with_resolved_fields(self, resolved_mocks, base_request):
        ctx = build_execution_context(
            "test_case_set_reviewer", base_request, MagicMock(), MagicMock(), _session_auth()
        )

        assert ctx.user_key == "U1"
        assert ctx.project_name == "My Project"
        assert ctx.project_key == "PROJ1"
        assert ctx.tov_key == "TOV1"
        assert ctx.cycle_key == "CYCLE1"
        assert ctx.language == "en"

    def test_user_key_comes_from_auth_info(self, resolved_mocks, base_request):
        ctx = build_execution_context(
            "uc", base_request, MagicMock(), MagicMock(), _session_auth(user_key="custom-user")
        )
        assert ctx.user_key == "custom-user"

    def test_request_language_overrides_config_language(self, resolved_mocks, base_request):
        base_request.language = "de"
        ctx = build_execution_context("uc", base_request, MagicMock(), MagicMock(), _session_auth())

        resolved_mocks["language"].assert_not_called()
        assert ctx.language == "de"

    def test_filtering_is_forwarded_to_context(self, resolved_mocks, base_request):
        filtering = FilteringOptions(appliedFilters=None)
        base_request.filtering = filtering
        ctx = build_execution_context("uc", base_request, MagicMock(), MagicMock(), _session_auth())

        assert ctx.filtering is filtering

    def test_unknown_project_raises_http_404(self, mocker, base_request):
        mocker.patch(
            "testbench_ai_service.utils.agent.get_project_name",
            side_effect=ValueError("Project not found"),
        )

        with pytest.raises(HTTPException) as exc_info:
            build_execution_context("uc", base_request, MagicMock(), MagicMock(), _session_auth())

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND


class TestBuildExecutionContextJwtToken:
    """JWT-token path of build_execution_context."""

    # A JWT whose payload contains {"scope": {"proj": "JP1", "tov": "JT1", "ccl": "JC1"}}
    _JWT = (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        ".eyJzY29wZSI6eyJwcm9qIjoiSlAxIiwidG92IjoiSlQxIiwiY2NsIjoiSkMxIn19"
        ".SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    )

    def test_keys_extracted_from_jwt_scope(self, resolved_mocks, base_request):
        ctx = build_execution_context(
            "uc", base_request, MagicMock(), MagicMock(), _jwt_auth(self._JWT)
        )

        assert ctx.project_key == "JP1"
        assert ctx.tov_key == "JT1"
        assert ctx.cycle_key == "JC1"

    def test_request_body_keys_are_ignored_for_jwt(self, resolved_mocks, base_request):
        base_request.project_key = "IGNORED"
        base_request.tov_key = "IGNORED"
        ctx = build_execution_context(
            "uc", base_request, MagicMock(), MagicMock(), _jwt_auth(self._JWT)
        )
        assert ctx.project_key == "JP1"

    def test_filtering_from_request_is_forwarded(self, resolved_mocks, base_request):
        filtering = FilteringOptions(appliedFilters=None)
        base_request.filtering = filtering
        ctx = build_execution_context(
            "uc", base_request, MagicMock(), MagicMock(), _jwt_auth(self._JWT)
        )
        assert ctx.filtering is filtering

    def test_invalid_jwt_raises_401(self, mocker, base_request):
        bad_jwt = "not.a.validjwt!!!"
        with pytest.raises(HTTPException) as exc_info:
            build_execution_context(
                "uc", base_request, MagicMock(), MagicMock(), _jwt_auth(bad_jwt)
            )
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED


class TestCheckMinTestbenchVersion:
    """Tests for ``check_min_testbench_version``."""

    @pytest.fixture(autouse=True)
    def setup(self):
        load_translations()

    @staticmethod
    def _conn(server_version: list[int]) -> MagicMock:
        conn = MagicMock()
        conn.server_version = server_version
        return conn

    @staticmethod
    def _context() -> MagicMock:
        context = MagicMock()
        context.language = LanguageOption.ENGLISH
        return context

    def test_exact_minimum_version_is_supported(self):
        conn = self._conn(list(MIN_TESTBENCH_VERSION))
        assert check_min_testbench_version(self._context(), conn) is None

    def test_newer_version_is_supported(self):
        conn = self._conn([*MIN_TESTBENCH_VERSION, 7])
        assert check_min_testbench_version(self._context(), conn) is None

    def test_double_digit_minor_version_is_supported(self):
        major, minor = MIN_TESTBENCH_VERSION[0], MIN_TESTBENCH_VERSION[1]
        conn = self._conn([major, minor + 9, 0])
        assert check_min_testbench_version(self._context(), conn) is None

    def test_outdated_version_returns_failed_precheck_result(self):
        major, minor = MIN_TESTBENCH_VERSION[0], MIN_TESTBENCH_VERSION[1]
        conn = self._conn([major, minor - 1, 9])

        result = check_min_testbench_version(self._context(), conn)

        assert result is not None
        assert result.passed is False
        assert result.items == []
        assert len(result.warnings) == 1

    def test_warning_names_both_the_current_and_required_version(self):
        conn = self._conn([3, 9, 1])

        result = check_min_testbench_version(self._context(), conn)

        assert result is not None
        warning = result.warnings[0]
        assert "3.9.1" in warning
        assert ".".join(map(str, MIN_TESTBENCH_VERSION)) in warning
