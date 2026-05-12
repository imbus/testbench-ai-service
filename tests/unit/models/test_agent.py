import unittest

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
        "prompt_config": PromptConfig(file="prompts/test.yaml", name="test"),
    }
    defaults.update(overrides)
    return ExecutionContext(**defaults)


class TestTriggerAgentRequest(unittest.TestCase):
    """Tests for ``TriggerAgentRequest``."""

    def test_minimal_valid_request(self):
        req = TriggerAgentRequest(project_key="P", tov_key="T", cycle_key="C")
        self.assertEqual(req.project_key, "P")
        self.assertIsNone(req.language)
        self.assertIsNone(req.root_uid)

    def test_language_field_accepts_language_option(self):
        req = TriggerAgentRequest(project_key="P", tov_key="T", language=LanguageOption.GERMAN)
        self.assertEqual(req.language, LanguageOption.GERMAN)

    def test_language_field_accepts_string_code(self):
        req = TriggerAgentRequest(project_key="P", tov_key="T", language="de")
        self.assertEqual(req.language, LanguageOption.GERMAN)


class TestTriggerAgentResponse(unittest.TestCase):
    """Tests for ``TriggerAgentResponse``."""

    def test_accepted_response(self):
        resp = TriggerAgentResponse(status="accepted", warnings=[])
        self.assertEqual(resp.status, "accepted")
        self.assertEqual(resp.warnings, [])

    def test_warnings_defaults_to_none(self):
        resp = TriggerAgentResponse(status="accepted")
        self.assertIsNone(resp.warnings)


class TestExecutionContext(unittest.TestCase):
    """Tests for ``ExecutionContext``."""

    def test_creates_with_all_required_fields(self):
        ctx = _make_execution_context()
        self.assertEqual(ctx.user_key, "u1")
        self.assertEqual(ctx.language, LanguageOption.ENGLISH)

    def test_cycle_key_and_root_uid_defaults_to_none(self):
        ctx = _make_execution_context()
        self.assertIsNone(ctx.cycle_key)
        self.assertIsNone(ctx.root_uid)


class TestPrecheckResult(unittest.TestCase):
    """Tests for ``PrecheckResult``."""

    def test_passed_result_has_empty_defaults(self):
        result = PrecheckResult(passed=True)
        self.assertTrue(result.passed)
        self.assertIsNone(result.items)
        self.assertEqual(result.warnings, [])

    def test_failed_result_can_carry_warnings(self):
        result = PrecheckResult(passed=False, warnings=["No test cases found"])
        self.assertFalse(result.passed)
        self.assertIn("No test cases found", result.warnings)


if __name__ == "__main__":
    unittest.main()
