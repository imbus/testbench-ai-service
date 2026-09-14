from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from testbench_ai_service.llm.anthropic import AnthropicClient
from testbench_ai_service.llm.base import RoutingFamily
from testbench_ai_service.llm.openai import AzureOpenAIClient, OpenAIClient
from testbench_ai_service.models.prompt import Message

MESSAGES = [Message(role="user", content="q")]


def _anthropic(model_routing=None) -> AnthropicClient:
    with patch("testbench_ai_service.llm.anthropic.AsyncAnthropic"):
        return AnthropicClient(api_key="k", model_routing=model_routing)


def _openai(model_routing=None) -> OpenAIClient:
    with patch("testbench_ai_service.llm.openai.AsyncOpenAI"):
        return OpenAIClient(api_key="k", model_routing=model_routing)


def _azure(model_routing=None, deployment_mapping=None) -> AzureOpenAIClient:
    with patch("testbench_ai_service.llm.openai.AsyncAzureOpenAI"):
        return AzureOpenAIClient(
            api_key="k",
            azure_endpoint="https://example.invalid/",
            api_version="2024-02-01",
            deployment_mapping=deployment_mapping,
            model_routing=model_routing,
        )


def _anthropic_text() -> MagicMock:
    block = MagicMock()
    block.type = "text"
    block.text = "hi"
    response = MagicMock()
    response.content = [block]
    return response


class TestAnthropicRoutingOverride:
    @pytest.mark.asyncio
    async def test_config_routes_a_model_the_frozensets_never_heard_of(self):
        client = _anthropic({"claude-opus-6": RoutingFamily.ADAPTIVE})
        client.client.messages.create = AsyncMock(return_value=_anthropic_text())

        await client.query_llm(model="claude-opus-6", messages=MESSAGES)

        kwargs = client.client.messages.create.call_args.kwargs
        assert kwargs["thinking"] == {"type": "adaptive"}

    @pytest.mark.asyncio
    async def test_an_unmapped_model_still_falls_back(self):
        client = _anthropic({})
        client.client.messages.create = AsyncMock(return_value=_anthropic_text())

        await client.query_llm(model="claude-unknown", messages=MESSAGES)

        kwargs = client.client.messages.create.call_args.kwargs
        assert "thinking" not in kwargs

    @pytest.mark.asyncio
    async def test_the_frozensets_still_apply_when_no_map_is_given(self):
        client = _anthropic(None)
        client.client.messages.create = AsyncMock(return_value=_anthropic_text())

        await client.query_llm(model="claude-opus-4-6", messages=MESSAGES)

        kwargs = client.client.messages.create.call_args.kwargs
        assert kwargs["thinking"] == {"type": "adaptive"}


class TestOpenAIRoutingOverride:
    @pytest.mark.asyncio
    async def test_config_routes_an_unknown_model_as_reasoning(self):
        client = _openai({"gpt-6": RoutingFamily.REASONING})
        response = AsyncMock()
        response.output_text = "hi"
        client.client.responses.create = AsyncMock(return_value=response)

        await client.query_llm(model="gpt-6", messages=MESSAGES)

        assert client.client.responses.create.await_count == 1


class TestAzureRoutingOverride:
    @pytest.mark.asyncio
    async def test_an_entry_may_name_the_deployment(self):
        client = _azure({"my-deployment": RoutingFamily.REASONING})
        response = AsyncMock()
        response.output_text = "hi"
        client.client.responses.create = AsyncMock(return_value=response)

        await client.query_llm(model="my-deployment", messages=MESSAGES)

        assert client.client.responses.create.await_count == 1

    @pytest.mark.asyncio
    async def test_an_entry_may_name_the_canonical_target(self):
        client = _azure(
            {"gpt-6": RoutingFamily.REASONING},
            deployment_mapping={"my-deployment": "gpt-6"},
        )
        response = AsyncMock()
        response.output_text = "hi"
        client.client.responses.create = AsyncMock(return_value=response)

        await client.query_llm(model="my-deployment", messages=MESSAGES)

        assert client.client.responses.create.await_count == 1
