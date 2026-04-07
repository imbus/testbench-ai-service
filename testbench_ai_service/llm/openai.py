from __future__ import annotations

from typing import Any, cast

from httpx import Timeout
from openai import AsyncOpenAI
from openai._constants import DEFAULT_MAX_RETRIES
from openai._types import (
    NOT_GIVEN,
    NotGiven,
)
from openai.types.responses import ResponseInputParam

from testbench_ai_service.llm.base import LLMClient
from testbench_ai_service.log import logger
from testbench_ai_service.models.prompt import Message

CHAT_MODELS: frozenset[str] = frozenset(
    {
        # Legacy GPT-3.5 (noch verfügbar, aber deprecated)
        "gpt-3.5-turbo",
        "gpt-3.5-turbo-0125",
        "gpt-3.5-turbo-1106",
        "gpt-3.5-turbo-16k",
        "gpt-3.5-turbo-instruct",
        "gpt-3.5-turbo-instruct-0914",
        # Legacy/Current GPT-4 (API verfügbar, ChatGPT retired)
        "gpt-4",
        "gpt-4-turbo",
        "gpt-4o",
        "gpt-4o-mini",
        # GPT-4.1 Familie (neu/current, 1M context)
        "gpt-4.1",
        "gpt-4.1-mini",
        "gpt-4.1-nano",
    }
)

REASONING_MODELS: frozenset[str] = frozenset(
    {
        # GPT-5 Reasoning/Codex (current)
        "gpt-5",
        "gpt-5-mini",
        "gpt-5-nano",
        "gpt-5-codex",
        "gpt-5-pro",
        "gpt-5.1",
        "gpt-5.1-codex",
        "gpt-5.1-codex-max",
        "gpt-5.1-codex-mini",
        "gpt-5.2",
        "gpt-5.2-codex",
        "gpt-5.2-pro",
        "gpt-5.3-chat-latest",
        "gpt-5.3-codex",
        "gpt-5.4",
        "gpt-5.4-pro",
        # o-Serie (dedicated reasoning, deep research)
        "o1",
        "o1-mini",
        "o1-preview",
        "o1-pro",
        "o3",
        "o3-mini",
        "o3-pro",
        "o3-deep-research",
        "o4-mini",
        "o4-mini-deep-research",
    }
)


class OpenAIClient(LLMClient):
    def __init__(
        self,
        api_key: str | None,
        timeout: float | Timeout | NotGiven | None = NOT_GIVEN,
        max_retries: int = DEFAULT_MAX_RETRIES,
        _strict_response_validation: bool = False,
    ):
        self.client = AsyncOpenAI(
            api_key=api_key,
            timeout=timeout,
            max_retries=max_retries,
            _strict_response_validation=_strict_response_validation,
        )

    async def query_llm(
        self,
        model: str,
        messages: list[Message],
        **kwargs: Any,
    ) -> str:
        input_messages = cast(ResponseInputParam, [message.model_dump() for message in messages])

        if model in CHAT_MODELS:
            return await self._query_chat_model(model, input_messages)

        if model in REASONING_MODELS:
            return await self._query_reasoning_model(
                model=model,
                input_messages=input_messages,
                reasoning_effort=kwargs.get("reasoning_effort", "medium"),
            )

        return await self._query_fallback_model(model, input_messages, **kwargs)

    async def _query_chat_model(self, model: str, input_messages: ResponseInputParam) -> str:
        return await self._create_response(
            model=model,
            input_data=input_messages,
            temperature=0,
            store=False,
        )

    async def _query_reasoning_model(
        self,
        model: str,
        input_messages: ResponseInputParam,
        reasoning_effort: str,
    ) -> str:
        return await self._create_response(
            model=model,
            input_data=input_messages,
            temperature=1,  # Reasoning models only support the default value of 1
            reasoning={
                "effort": reasoning_effort  # low, medium (default), high (expensive)
            },
            store=False,
        )

    async def _query_fallback_model(
        self,
        model: str,
        input_messages: ResponseInputParam,
        **kwargs: Any,
    ) -> str:
        logger.warning(
            "Model '%s' is not explicitly supported. Attempting a fallback request.", model
        )
        try:
            return await self._create_response(
                model=model,
                input_data=input_messages,
                **kwargs,
            )
        except Exception as e:
            raise RuntimeError(f"Fallback request failed for model '{model}': {e}") from e

    async def _create_response(
        self, model: str, input_data: str | ResponseInputParam, **kwargs: Any
    ) -> str:
        response = await self.client.responses.create(
            model=model,
            input=input_data,
            **kwargs,
        )
        output_text = response.output_text
        if not output_text:
            raise RuntimeError(f"Model '{model}' returned an empty response.")
        return str(output_text)

    async def close(self):
        await self.client.close()
