import unittest
from abc import ABC

from testbench_ai_service.llm.base import LLMClient, LLMProvider


class TestLLMProvider(unittest.TestCase):
    """Tests for the ``LLMProvider`` enum."""

    def test_openai_value(self):
        self.assertEqual(LLMProvider.OPENAI.value, "openai")

    def test_custom_value(self):
        self.assertEqual(LLMProvider.CUSTOM.value, "custom")

    def test_azure_openai_value(self):
        self.assertEqual(LLMProvider.AZURE_OPENAI.value, "azure_openai")

    def test_str_returns_value(self):
        self.assertEqual(str(LLMProvider.OPENAI), "openai")

    def test_is_string_subclass(self):
        self.assertIsInstance(LLMProvider.OPENAI, str)


class TestLLMClient(unittest.TestCase):
    """Tests for the ``LLMClient`` abstract base class."""

    def test_is_abstract(self):
        self.assertTrue(issubclass(LLMClient, ABC))

    def test_cannot_instantiate_directly(self):
        with self.assertRaises(TypeError):
            LLMClient()  # type: ignore[abstract]

    def test_concrete_subclass_must_implement_all_abstract_methods(self):
        """A partial implementation raises TypeError at instantiation."""

        class _Partial(LLMClient):
            def __init__(self, api_key=None):
                pass

            # Missing query_llm and close

        with self.assertRaises(TypeError):
            _Partial()


if __name__ == "__main__":
    unittest.main()
