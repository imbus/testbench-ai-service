from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from anthropic.types import OutputTokensDetails as AnthropicOutputDetails
from anthropic.types import Usage as AnthropicUsage
from openai.types.responses import ResponseUsage
from openai.types.responses.response_usage import OutputTokensDetails

from testbench_ai_service.llm.anthropic import AnthropicClient
from testbench_ai_service.llm.base import LLMClient, LLMResult, TokenUsage, token_count
from testbench_ai_service.llm.openai import OpenAIClient
from testbench_ai_service.models.prompt import Message

MESSAGES = [Message(role="user", content="q")]


def _anthropic_client() -> AnthropicClient:
    with patch("testbench_ai_service.llm.anthropic.AsyncAnthropic"):
        return AnthropicClient(api_key="k")


def _anthropic_response(usage) -> MagicMock:
    block = MagicMock()
    block.type = "text"
    block.text = "hi"
    response = MagicMock()
    response.content = [block]
    response.usage = usage
    return response


def _openai_client() -> OpenAIClient:
    with patch("testbench_ai_service.llm.openai.AsyncOpenAI"):
        return OpenAIClient(api_key="k")


def _openai_response(usage) -> MagicMock:
    response = MagicMock()
    response.output_text = "hi"
    response.usage = usage
    return response


class TestTokenCount:
    @pytest.mark.parametrize("value", [None, "12", 1.5, True, MagicMock()])
    def test_anything_but_an_int_is_not_a_count(self, value):
        assert token_count(value) is None

    def test_an_int_is_a_count(self):
        assert token_count(0) == 0


class TestBaseDefault:
    @pytest.mark.asyncio
    async def test_a_custom_client_reports_no_usage(self):
        class Custom(LLMClient):
            def __init__(self, api_key=None):
                pass

            async def query_llm(self, model, messages, *args, **kwargs):
                return "custom"

            async def close(self):
                pass

        assert await Custom().query_llm_with_usage("m", MESSAGES) == LLMResult(text="custom")


class TestAnthropicUsage:
    @pytest.mark.asyncio
    async def test_cache_tokens_are_folded_into_the_input(self):
        client = _anthropic_client()
        usage = AnthropicUsage(
            input_tokens=10,
            output_tokens=50,
            cache_creation_input_tokens=100,
            cache_read_input_tokens=1000,
            output_tokens_details=AnthropicOutputDetails(thinking_tokens=30),
        )
        client.client.messages.create = AsyncMock(return_value=_anthropic_response(usage))

        result = await client.query_llm_with_usage("claude-opus-5", MESSAGES)

        assert result == LLMResult(
            text="hi",
            usage=TokenUsage(input_tokens=1110, output_tokens=50, reasoning_tokens=30),
        )

    @pytest.mark.asyncio
    async def test_missing_details_leave_reasoning_unreported(self):
        client = _anthropic_client()
        usage = AnthropicUsage(input_tokens=10, output_tokens=50)
        client.client.messages.create = AsyncMock(return_value=_anthropic_response(usage))

        result = await client.query_llm_with_usage("claude-opus-5", MESSAGES)

        assert result.usage == TokenUsage(input_tokens=10, output_tokens=50)

    @pytest.mark.asyncio
    async def test_query_llm_still_returns_only_the_text(self):
        client = _anthropic_client()
        usage = AnthropicUsage(input_tokens=10, output_tokens=50)
        client.client.messages.create = AsyncMock(return_value=_anthropic_response(usage))

        assert await client.query_llm("claude-opus-5", MESSAGES) == "hi"


class TestOpenAIUsage:
    @pytest.mark.asyncio
    async def test_reports_input_output_and_reasoning(self):
        client = _openai_client()
        # model_construct: the input details' required fields change between
        # SDK releases and are irrelevant to what is read here.
        usage = ResponseUsage.model_construct(
            input_tokens=200,
            output_tokens=80,
            output_tokens_details=OutputTokensDetails(reasoning_tokens=64),
            total_tokens=280,
        )
        client.client.responses.create = AsyncMock(return_value=_openai_response(usage))

        result = await client.query_llm_with_usage("o3", MESSAGES)

        assert result == LLMResult(
            text="hi",
            usage=TokenUsage(input_tokens=200, output_tokens=80, reasoning_tokens=64),
        )

    @pytest.mark.asyncio
    async def test_a_response_without_usage_reports_none(self):
        # Compatible endpoints may omit usage; the text must still come back.
        client = _openai_client()
        client.client.responses.create = AsyncMock(return_value=_openai_response(None))

        result = await client.query_llm_with_usage("gpt-4o", MESSAGES)

        assert result == LLMResult(text="hi")
