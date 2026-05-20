import pytest
from pydantic import ValidationError

from testbench_ai_service.models.prompt import (
    Message,
    MessageTemplate,
    Prompt,
    PromptDefinition,
    PromptVariant,
)


class TestMessageTemplate:
    """Tests for the ``MessageTemplate`` model."""

    def test_default_role_is_user(self):
        template = MessageTemplate(text="Hello")
        assert template.role == "user"

    def test_system_role_is_accepted(self):
        template = MessageTemplate(role="system", text="You are a helpful assistant.")
        assert template.role == "system"

    def test_invalid_role_raises_validation_error(self):
        with pytest.raises(ValidationError):
            MessageTemplate(role="unknown", text="bad")


class TestPromptVariant:
    """Tests for the ``PromptVariant`` model."""

    def test_valid_variant(self):
        variant = PromptVariant(
            name="default", model="gpt-4o", messages=[MessageTemplate(text="Hello")]
        )
        assert variant.name == "default"
        assert len(variant.messages) == 1


class TestPromptDefinition:
    """Tests for the ``PromptDefinition`` model."""

    def _make_variant(self, name="v1"):
        return PromptVariant(name=name, model="gpt-4o", messages=[MessageTemplate(text="Hi")])

    def test_valid_definition(self):
        defn = PromptDefinition(
            name="my-prompt",
            default_model="gpt-4o",
            default_variant="v1",
            variants=[self._make_variant()],
        )
        assert defn.name == "my-prompt"

    def test_empty_variants_raises_validation_error(self):
        with pytest.raises(ValidationError):
            PromptDefinition(name="p", default_model="gpt-4o", default_variant="v1", variants=[])

    def test_description_defaults_to_none(self):
        defn = PromptDefinition(
            name="p", default_model="gpt-4o", default_variant="v1", variants=[self._make_variant()]
        )
        assert defn.description is None


class TestMessage:
    """Tests for the ``Message`` model."""

    def test_default_role_is_user(self):
        msg = Message(content="Hello")
        assert msg.role == "user"

    def test_assistant_role(self):
        msg = Message(role="assistant", content="Response")
        assert msg.role == "assistant"


class TestPrompt:
    """Tests for the ``Prompt`` model."""

    def test_stores_model_name_and_messages(self):
        prompt = Prompt(
            model_name="gpt-4o",
            messages=[Message(role="user", content="Hello")],
        )
        assert prompt.model_name == "gpt-4o"
        assert len(prompt.messages) == 1
