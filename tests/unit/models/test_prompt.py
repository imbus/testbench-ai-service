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

    def test_duplicate_variant_names_are_rejected(self):
        # At runtime the first variant of a name wins, the other is dead.
        with pytest.raises(ValidationError, match="Duplicate variant names: v1"):
            PromptDefinition(
                name="p",
                default_model="gpt-4o",
                default_variant="v1",
                variants=[self._make_variant("v1"), self._make_variant("v1")],
            )

    def test_blank_variant_name_is_rejected(self):
        with pytest.raises(ValidationError, match="Variant names must not be empty"):
            PromptDefinition(
                name="p",
                default_model="gpt-4o",
                default_variant="v1",
                variants=[self._make_variant("v1"), self._make_variant(" ")],
            )

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


def _message(text="hi"):
    return {"role": "user", "text": text}


class TestPromptVariantSteps:
    def test_a_variant_with_steps_and_no_messages_is_valid(self):
        variant = PromptVariant(name="A", messages=[], steps={"one": [_message()]})

        assert variant.templates_for("one")[0].text == "hi"

    def test_without_a_step_the_messages_are_used(self):
        variant = PromptVariant(name="A", messages=[_message("plain")])

        assert variant.templates_for(None)[0].text == "plain"
        assert variant.steps == {}

    def test_messages_and_steps_together_are_rejected(self):
        with pytest.raises(ValidationError, match="either 'messages' or 'steps'"):
            PromptVariant(name="A", messages=[_message()], steps={"one": [_message()]})

    def test_a_step_without_messages_is_rejected(self):
        with pytest.raises(ValidationError, match="Steps without messages: one"):
            PromptVariant(name="A", messages=[], steps={"one": []})

    def test_an_unknown_step_raises_value_error(self):
        variant = PromptVariant(name="A", messages=[], steps={"one": [_message()]})

        with pytest.raises(ValueError, match="Step 'two' not found in variant 'A'"):
            variant.templates_for("two")
