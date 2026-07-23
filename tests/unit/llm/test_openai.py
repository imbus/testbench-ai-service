from unittest.mock import AsyncMock, patch

from testbench_ai_service.llm.openai import (
    CHAT_MODELS,
    REASONING_MODELS,
    AzureOpenAIClient,
    OpenAIClient,
)
from testbench_ai_service.models.prompt import Message


class TestModelSets:
    """Sanity checks for the declared model sets."""

    def test_chat_models_is_non_empty_frozenset(self):
        assert isinstance(CHAT_MODELS, frozenset)
        assert len(CHAT_MODELS) > 0

    def test_reasoning_models_is_non_empty_frozenset(self):
        assert isinstance(REASONING_MODELS, frozenset)
        assert len(REASONING_MODELS) > 0

    def test_sets_are_disjoint(self):
        """No model should appear in both CHAT_MODELS and REASONING_MODELS."""
        overlap = CHAT_MODELS & REASONING_MODELS
        assert overlap == frozenset(), f"Overlapping models: {overlap}"

    def test_known_chat_model_is_in_chat_models(self):
        assert "gpt-4o" in CHAT_MODELS

    def test_known_reasoning_model_is_in_reasoning_models(self):
        assert "o1" in REASONING_MODELS


class TestOpenAIClientQueryLlm:
    """Tests for ``OpenAIClient.query_llm``."""

    def _make_client(self):
        with patch("testbench_ai_service.llm.openai.AsyncOpenAI"):
            return OpenAIClient(api_key="test-key")

    async def test_chat_model_uses_chat_completions(self):
        """Chat models call _create_response which routes through client.responses.create."""
        client = self._make_client()
        mock_response = AsyncMock()
        mock_response.output_text = "Chat response"
        client.client.responses.create = AsyncMock(return_value=mock_response)

        messages = [Message(role="user", content="Hello")]
        result = await client.query_llm("gpt-4o", messages)
        assert result == "Chat response"
        client.client.responses.create.assert_awaited_once()

    async def test_reasoning_model_uses_responses_api(self):
        client = self._make_client()
        mock_response = AsyncMock()
        mock_response.output_text = "Reasoning response"
        client.client.responses.create = AsyncMock(return_value=mock_response)

        messages = [Message(role="user", content="Reason about this")]
        result = await client.query_llm("o1", messages)
        assert result == "Reasoning response"
        client.client.responses.create.assert_awaited_once()

    @patch("testbench_ai_service.llm.openai.logger")
    async def test_logs_llm_response_duration(self, mock_logger):
        client = self._make_client()
        mock_response = AsyncMock()
        mock_response.output_text = "Chat response"
        client.client.responses.create = AsyncMock(return_value=mock_response)

        await client.query_llm("gpt-4o", [Message(role="user", content="Hello")])

        log_messages = [call.args[0] for call in mock_logger.debug.call_args_list]
        assert any("LLM request: OpenAI" in message for message in log_messages)
        assert any("LLM response: OpenAI" in message for message in log_messages)


class TestAzureOpenAIClientQueryLlm:
    """Tests for ``AzureOpenAIClient``."""

    def _make_client(self):
        with patch("testbench_ai_service.llm.openai.AsyncAzureOpenAI"):
            return AzureOpenAIClient(
                api_key="test-key",
                azure_endpoint="https://example.openai.azure.com",
                api_version="2024-10-21",
            )

    async def test_chat_model_uses_responses_api(self):
        client = self._make_client()
        mock_response = AsyncMock()
        mock_response.output_text = "Azure chat response"
        client.client.responses.create = AsyncMock(return_value=mock_response)

        messages = [Message(role="user", content="Hello Azure")]
        result = await client.query_llm("gpt-4o", messages)

        assert result == "Azure chat response"
        client.client.responses.create.assert_awaited_once()
