from abc import ABC

import pytest

from testbench_ai_service.llm.base import LLMClient, LLMProvider


class TestLLMProvider:
    """Tests for the ``LLMProvider`` enum."""

    def test_openai_value(self):
        assert LLMProvider.OPENAI.value == "openai"

    def test_custom_value(self):
        assert LLMProvider.CUSTOM.value == "custom"

    def test_azure_openai_value(self):
        assert LLMProvider.AZURE_OPENAI.value == "azure_openai"

    def test_str_returns_value(self):
        assert str(LLMProvider.OPENAI) == "openai"

    def test_is_string_subclass(self):
        assert isinstance(LLMProvider.OPENAI, str)


class TestLLMClient:
    """Tests for the ``LLMClient`` abstract base class."""

    def test_is_abstract(self):
        assert issubclass(LLMClient, ABC)

    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            LLMClient()  # type: ignore[abstract]

    def test_concrete_subclass_must_implement_all_abstract_methods(self):
        """A partial implementation raises TypeError at instantiation."""

        class _Partial(LLMClient):
            def __init__(self, api_key=None):
                pass

            # Missing query_llm and close

        with pytest.raises(TypeError):
            _Partial()
