import logging
import os
from pathlib import Path

import pytest

from testbench_ai_service.models.config import PromptConfig
from testbench_ai_service.models.prompt import MessageTemplate
from testbench_ai_service.utils.build_prompt_utils import build_messages, build_prompt
from testbench_ai_service.utils.prompt_utils import get_prompt_definition

_DATA_DIR = Path(__file__).parent / "data"
_DUMMY_PROMPT_PATH = _DATA_DIR / "dummy_prompt.yaml"


class TestGetPromptDefinition:
    """get_prompt_definition loads an entry from a YAML prompt file."""

    def test_missing_file_raises_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            get_prompt_definition("nonexistent.yaml")


class TestBuildPrompt:
    """build_prompt assembles a Prompt (messages + model) from a PromptConfig."""

    def _make_config(self, **kwargs) -> PromptConfig:
        defaults = {
            "file": _DUMMY_PROMPT_PATH,
        }
        defaults.update(kwargs)
        return PromptConfig(**defaults)  # type: ignore[arg-type]

    def test_model_name_is_read_from_prompt_definition(self):
        prompt = build_prompt(
            prompt_config=self._make_config(), agent_data={"test_case_set": "Some test case set."}
        )
        assert prompt.model_name == "o4-mini-2025-04-16"

    def test_default_variant_produces_system_and_user_messages(self):
        prompt = build_prompt(
            prompt_config=self._make_config(), agent_data={"test_case_set": "Some test case set."}
        )
        messages = prompt.messages
        assert len(messages) == 2
        assert messages[0].role == "system"
        assert messages[1].role == "user"
        assert "You will receive a blueprint" in messages[0].content
        assert "Review the following test case" in messages[1].content

    def test_vars_are_substituted_in_messages(self):
        config = self._make_config(
            vars={
                "glossary": "Some glossary.",
                "test_case_set_description": "Some description.",
            },
        )
        prompt = build_prompt(
            prompt_config=config, agent_data={"test_case_set": "Some test case set."}
        )
        user_content = prompt.messages[1].content
        assert "Some glossary." in user_content
        assert "Some description." in user_content
        assert "Some test case set." in user_content

    def test_non_default_variant_produces_single_user_message(self):
        config = self._make_config(variant="DEU")
        prompt = build_prompt(
            prompt_config=config, agent_data={"test_case_set": "Some test case set."}
        )
        messages = prompt.messages
        assert len(messages) == 1
        assert messages[0].role == "user"
        assert "Prüfe den folgenden Testfall:" in messages[0].content

    def test_vars_with_special_characters_is_preserved(self):
        prompt = build_prompt(
            prompt_config=self._make_config(), agent_data={"test_case_set": "${robot_variable}"}
        )
        assert "${robot_variable}" in prompt.messages[1].content

    def test_unknown_variant_raises_value_error(self):
        with pytest.raises(ValueError, match="not found in prompt"):
            build_prompt(prompt_config=self._make_config(variant="SomethingSomething"))

    def test_missing_prompt_file_raises_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            get_prompt_definition("nonexistent.yaml")


class TestBuildMessagesSandbox:
    """Runtime rendering is sandboxed: project admins can save fork templates,
    so a template must never reach Python internals through dunder traversal."""

    _PAYLOAD = "{{ cycler.__init__.__globals__.os.getpid() }}"

    def test_dunder_traversal_in_inline_template_does_not_execute(self, caplog):
        template = MessageTemplate(role="user", text=self._PAYLOAD)
        with caplog.at_level(logging.ERROR):
            messages = build_messages([template], {}, {}, Path())
        assert str(os.getpid()) not in messages[0].content
        # Same failure path as a broken template: the raw text, not a render.
        assert messages[0].content == self._PAYLOAD
        assert any("unsafe" in r.getMessage() for r in caplog.records)

    def test_dunder_traversal_in_file_template_does_not_execute(self, tmp_path):
        (tmp_path / "evil.jinja").write_text(self._PAYLOAD, encoding="utf-8")
        template = MessageTemplate(role="user", file="evil.jinja")
        messages = build_messages([template], {}, {}, tmp_path)
        assert str(os.getpid()) not in messages[0].content
        assert messages[0].content == ""

    def test_mutating_builtin_methods_are_refused(self):
        template = MessageTemplate(role="user", text="{% set x = [] %}{{ x.append(1) }}{{ x }}")
        messages = build_messages([template], {}, {}, Path())
        assert "[1]" not in messages[0].content
