from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from testbench_ai_service.llm.anthropic import (
    ADAPTIVE_THINKING_MODELS,
    BUDGET_THINKING_MODELS,
    AnthropicClient,
)
from testbench_ai_service.models.prompt import Message

CURRENT_ADAPTIVE = ["claude-opus-5", "claude-sonnet-5", "claude-fable-5-1"]


def _client() -> AnthropicClient:
    with patch("testbench_ai_service.llm.anthropic.AsyncAnthropic"):
        return AnthropicClient(api_key="k")


def _text_response(text: str = "hi") -> MagicMock:
    block = MagicMock()
    block.type = "text"
    block.text = text
    response = MagicMock()
    response.content = [block]
    return response


class TestCurrentGenerationIsRouted:
    @pytest.mark.parametrize("model", CURRENT_ADAPTIVE)
    def test_is_in_the_adaptive_set(self, model):
        assert model in ADAPTIVE_THINKING_MODELS

    def test_haiku_stays_on_the_budget_path(self):
        # Haiku 4.5 is the one current model that still takes budget_tokens.
        assert "claude-haiku-4-5" in BUDGET_THINKING_MODELS
        assert "claude-haiku-4-5" not in ADAPTIVE_THINKING_MODELS

    def test_the_two_sets_stay_disjoint(self):
        assert not (BUDGET_THINKING_MODELS & ADAPTIVE_THINKING_MODELS)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("model", CURRENT_ADAPTIVE)
    async def test_sends_adaptive_thinking_not_the_fallback_shape(self, model):
        client = _client()
        client.client.messages.create = AsyncMock(return_value=_text_response())

        await client.query_llm(model=model, messages=[Message(role="user", content="q")])

        kwargs = client.client.messages.create.call_args.kwargs
        assert kwargs["thinking"] == {"type": "adaptive"}
        assert kwargs["output_config"] == {"effort": "high"}
        # The fallback path would have left max_tokens at _create_response's 4096.
        assert kwargs["max_tokens"] == 16000

    @pytest.mark.asyncio
    @patch("testbench_ai_service.llm.anthropic.logger")
    async def test_does_not_warn_about_an_unsupported_model(self, mock_logger):
        client = _client()
        client.client.messages.create = AsyncMock(return_value=_text_response())

        await client.query_llm(model="claude-opus-5", messages=[Message(role="user", content="q")])

        warnings = " ".join(str(call) for call in mock_logger.warning.call_args_list)
        assert "not explicitly supported" not in warnings
