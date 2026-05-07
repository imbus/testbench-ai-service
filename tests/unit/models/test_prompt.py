import unittest

from pydantic import ValidationError

from testbench_ai_service.models.prompt import (
    Block,
    Message,
    Prompt,
    PromptDefinition,
    PromptVariant,
)


class TestBlock(unittest.TestCase):
    """Tests for the ``Block`` model."""

    def test_default_role_is_user(self):
        block = Block(text="Hello")
        self.assertEqual(block.role, "user")

    def test_system_role_is_accepted(self):
        block = Block(role="system", text="You are a helpful assistant.")
        self.assertEqual(block.role, "system")

    def test_invalid_role_raises_validation_error(self):
        with self.assertRaises(ValidationError):
            Block(role="unknown", text="bad")


class TestPromptVariant(unittest.TestCase):
    """Tests for the ``PromptVariant`` model."""

    def test_valid_variant(self):
        variant = PromptVariant(name="default", model="gpt-4o", blocks=[Block(text="Hello")])
        self.assertEqual(variant.name, "default")
        self.assertEqual(len(variant.blocks), 1)


class TestPromptDefinition(unittest.TestCase):
    """Tests for the ``PromptDefinition`` model."""

    def _make_variant(self, name="v1"):
        return PromptVariant(name=name, model="gpt-4o", blocks=[Block(text="Hi")])

    def test_valid_definition(self):
        defn = PromptDefinition(
            name="my-prompt",
            default_model="gpt-4o",
            default_variant="v1",
            variants=[self._make_variant()],
        )
        self.assertEqual(defn.name, "my-prompt")

    def test_empty_variants_raises_validation_error(self):
        with self.assertRaises(ValidationError):
            PromptDefinition(name="p", default_model="gpt-4o", default_variant="v1", variants=[])

    def test_description_defaults_to_none(self):
        defn = PromptDefinition(
            name="p", default_model="gpt-4o", default_variant="v1", variants=[self._make_variant()]
        )
        self.assertIsNone(defn.description)


class TestMessage(unittest.TestCase):
    """Tests for the ``Message`` model."""

    def test_default_role_is_user(self):
        msg = Message(content="Hello")
        self.assertEqual(msg.role, "user")

    def test_assistant_role(self):
        msg = Message(role="assistant", content="Response")
        self.assertEqual(msg.role, "assistant")


class TestPrompt(unittest.TestCase):
    """Tests for the ``Prompt`` model."""

    def test_stores_model_name_and_messages(self):
        prompt = Prompt(
            model_name="gpt-4o",
            messages=[Message(role="user", content="Hello")],
        )
        self.assertEqual(prompt.model_name, "gpt-4o")
        self.assertEqual(len(prompt.messages), 1)


if __name__ == "__main__":
    unittest.main()
