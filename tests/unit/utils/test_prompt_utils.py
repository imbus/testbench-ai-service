import unittest
from pathlib import Path

from testbench_ai_service.config import PromptConfig
from testbench_ai_service.utils.prompt_utils import build_prompt, get_prompt_definition

_DATA_DIR = Path(__file__).parent / "data"
_DUMMY_PROMPT_PATH = _DATA_DIR / "dummy_prompt.yaml"
_PROMPT_NAME = "TestCaseSetReviewer"


class TestGetPromptDefinition(unittest.TestCase):
    """get_prompt_definition loads a named entry from a YAML prompt file."""

    def test_missing_file_raises_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            get_prompt_definition("nonexistent.yaml", _PROMPT_NAME)

    def test_missing_prompt_name_raises_value_error(self):
        with self.assertRaises(ValueError):
            get_prompt_definition(_DUMMY_PROMPT_PATH, "NoSuchPrompt")


class TestBuildPrompt(unittest.TestCase):
    """build_prompt assembles a Prompt (messages + model) from a PromptConfig."""

    def _make_config(self, **kwargs) -> PromptConfig:
        defaults = {
            "file": _DUMMY_PROMPT_PATH,
            "name": _PROMPT_NAME,
        }
        defaults.update(kwargs)
        return PromptConfig(**defaults)  # type: ignore[arg-type]

    def test_model_name_is_read_from_prompt_definition(self):
        prompt = build_prompt(
            prompt_config=self._make_config(), agent_data={"test_case": "Some test case."}
        )
        self.assertEqual(prompt.model_name, "o4-mini-2025-04-16")

    def test_default_variant_produces_system_and_user_messages(self):
        prompt = build_prompt(
            prompt_config=self._make_config(), agent_data={"test_case": "Some test case."}
        )
        messages = prompt.messages
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0].role, "system")
        self.assertEqual(messages[1].role, "user")
        self.assertIn("You will receive a blueprint", messages[0].content)
        self.assertIn("Review the following test case", messages[1].content)

    def test_vars_are_substituted_in_messages(self):
        config = self._make_config(
            vars={
                "glossary": "Some glossary.",
                "test_case_set_description": "Some description.",
            },
        )
        prompt = build_prompt(prompt_config=config, agent_data={"test_case": "Some test case."})
        user_content = prompt.messages[1].content
        self.assertIn("Some glossary.", user_content)
        self.assertIn("Some description.", user_content)
        self.assertIn("Some test case.", user_content)

    def test_non_default_variant_produces_single_user_message(self):
        config = self._make_config(variant="DEU")
        prompt = build_prompt(prompt_config=config, agent_data={"test_case": "Some test."})
        messages = prompt.messages
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].role, "user")
        self.assertIn("Prüfe den folgenden Testfall:", messages[0].content)

    def test_vars_with_special_characters_is_preserved(self):
        prompt = build_prompt(
            prompt_config=self._make_config(), agent_data={"test_case": "${robot_variable}"}
        )
        self.assertIn("${robot_variable}", prompt.messages[1].content)

    def test_unknown_prompt_name_raises_value_error(self):
        with self.assertRaises(ValueError):
            build_prompt(prompt_config=self._make_config(name="UnknownPrompt"))

    def test_unknown_variant_raises_value_error(self):
        with self.assertRaises(ValueError):
            build_prompt(prompt_config=self._make_config(variant="SomethingSomething"))

    def test_missing_prompt_file_raises_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            get_prompt_definition("nonexistent.yaml", _PROMPT_NAME)


if __name__ == "__main__":
    unittest.main()
