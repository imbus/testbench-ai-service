from testbench_ai_service.config import LLMConfig, PromptConfig
from testbench_ai_service.llm.base import LLMProvider
from testbench_ai_service.models.agent import (
    ExecutionContext,
    PrecheckResult,
    TriggerAgentRequest,
    TriggerAgentResponse,
)
from testbench_ai_service.models.language import LanguageOption


def _make_execution_context(**overrides):
    defaults = {
        "user_key": "u1",
        "project_name": "Project",
        "project_key": "pk",
        "tov_key": "tv1",
        "language": LanguageOption.ENGLISH,
        "llm_config": LLMConfig(provider=LLMProvider.OPENAI, model="gpt-4o"),
        "prompt_config": PromptConfig(file="prompts/test.yaml"),
    }
    defaults.update(overrides)
    return ExecutionContext(**defaults)


class TestTriggerAgentRequest:
    """Tests for ``TriggerAgentRequest``."""

    def test_minimal_valid_request(self):
        req = TriggerAgentRequest(project_key="P", tov_key="T", cycle_key="C")
        assert req.project_key == "P"
        assert req.language is None
        assert req.root_uid is None

    def test_language_field_accepts_language_option(self):
        req = TriggerAgentRequest(project_key="P", tov_key="T", language=LanguageOption.GERMAN)
        assert req.language == LanguageOption.GERMAN

    def test_language_field_accepts_string_code(self):
        req = TriggerAgentRequest(project_key="P", tov_key="T", language="de")
        assert req.language == LanguageOption.GERMAN


class TestTriggerAgentResponse:
    """Tests for ``TriggerAgentResponse``."""

    def test_accepted_response(self):
        resp = TriggerAgentResponse(status="accepted", warnings=[])
        assert resp.status == "accepted"
        assert resp.warnings == []

    def test_warnings_defaults_to_none(self):
        resp = TriggerAgentResponse(status="accepted")
        assert resp.warnings is None


class TestExecutionContext:
    """Tests for ``ExecutionContext``."""

    def test_creates_with_all_required_fields(self):
        ctx = _make_execution_context()
        assert ctx.user_key == "u1"
        assert ctx.language == LanguageOption.ENGLISH

    def test_cycle_key_and_root_uid_defaults_to_none(self):
        ctx = _make_execution_context()
        assert ctx.cycle_key is None
        assert ctx.root_uid is None


class TestPrecheckResult:
    """Tests for ``PrecheckResult``."""

    def test_passed_result_has_empty_defaults(self):
        result = PrecheckResult(passed=True)
        assert result.passed
        assert result.items == []
        assert result.warnings == []

    def test_failed_result_can_carry_warnings(self):
        result = PrecheckResult(passed=False, warnings=["No test cases found"])
        assert not (result.passed)
        assert "No test cases found" in result.warnings
