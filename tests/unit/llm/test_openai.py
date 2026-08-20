from unittest.mock import AsyncMock, MagicMock, patch

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


class TestAzureOpenAIClientAuthentication:
    """Tests for how ``AzureOpenAIClient`` passes credentials to the SDK."""

    def test_api_key_mode_passes_key_and_no_token_provider(self):
        with patch("testbench_ai_service.llm.openai.AsyncAzureOpenAI") as mock_sdk:
            AzureOpenAIClient(
                api_key="test-key",
                azure_endpoint="https://example.openai.azure.com",
                api_version="2024-10-21",
            )

        kwargs = mock_sdk.call_args.kwargs
        assert kwargs["api_key"] == "test-key"
        assert kwargs["azure_ad_token_provider"] is None

    def test_entra_id_mode_passes_token_provider_and_no_api_key(self):
        token_provider = MagicMock(name="token_provider")

        with patch("testbench_ai_service.llm.openai.AsyncAzureOpenAI") as mock_sdk:
            AzureOpenAIClient(
                api_key=None,
                azure_endpoint="https://example.openai.azure.com",
                api_version="2024-10-21",
                azure_ad_token_provider=token_provider,
                credential=AsyncMock(),
            )

        kwargs = mock_sdk.call_args.kwargs
        assert kwargs["api_key"] is None
        assert kwargs["azure_ad_token_provider"] is token_provider

    async def test_close_closes_client_and_credential(self):
        credential = AsyncMock()

        with patch("testbench_ai_service.llm.openai.AsyncAzureOpenAI"):
            client = AzureOpenAIClient(
                api_key=None,
                azure_endpoint="https://example.openai.azure.com",
                api_version="2024-10-21",
                azure_ad_token_provider=MagicMock(),
                credential=credential,
            )
        client.client.close = AsyncMock()

        await client.close()

        client.client.close.assert_awaited_once()
        credential.close.assert_awaited_once()

    async def test_close_without_credential_closes_only_the_client(self):
        with patch("testbench_ai_service.llm.openai.AsyncAzureOpenAI"):
            client = AzureOpenAIClient(
                api_key="test-key",
                azure_endpoint="https://example.openai.azure.com",
                api_version="2024-10-21",
            )
        client.client.close = AsyncMock()

        await client.close()

        client.client.close.assert_awaited_once()

    def test_deployment_mapping_still_defaults_to_empty_dict(self):
        with patch("testbench_ai_service.llm.openai.AsyncAzureOpenAI"):
            client = AzureOpenAIClient(
                api_key="test-key",
                azure_endpoint="https://example.openai.azure.com",
                api_version="2024-10-21",
            )

        assert client.deployment_mapping == {}
