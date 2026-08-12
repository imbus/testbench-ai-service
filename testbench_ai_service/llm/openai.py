from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, cast

from httpx import Timeout
from openai import AsyncAzureOpenAI, AsyncOpenAI
from openai._constants import DEFAULT_MAX_RETRIES
from openai._types import (
    NOT_GIVEN,
    NotGiven,
)
from openai.types.responses import ResponseInputParam

from testbench_ai_service.llm.base import LLMClient
from testbench_ai_service.log import logger
from testbench_ai_service.models.prompt import Message

if TYPE_CHECKING:
    from azure.core.credentials_async import AsyncTokenCredential
    from openai.lib.azure import AsyncAzureADTokenProvider

CHAT_MODELS: frozenset[str] = frozenset(
    {
        "gpt-3.5-turbo",
        "gpt-3.5-turbo-0125",
        "gpt-3.5-turbo-1106",
        "gpt-3.5-turbo-16k",
        "gpt-3.5-turbo-instruct",
        "gpt-3.5-turbo-instruct-0914",
        "gpt-4",
        "gpt-4-0613",
        "gpt-4-turbo",
        "gpt-4-turbo-2024-04-09",
        "gpt-4.1",
        "gpt-4.1-2025-04-14",
        "gpt-4.1-mini",
        "gpt-4.1-mini-2025-04-14",
        "gpt-4.1-nano",
        "gpt-4.1-nano-2025-04-14",
        "gpt-4o",
        "gpt-4o-2024-05-13",
        "gpt-4o-2024-08-06",
        "gpt-4o-2024-11-20",
        "gpt-4o-mini",
        "gpt-4o-mini-2024-07-18",
        "gpt-4o-mini-search-preview",
        "gpt-4o-mini-search-preview-2025-03-11",
        "gpt-4o-search-preview",
        "gpt-4o-search-preview-2025-03-11",
    }
)

REASONING_MODELS: frozenset[str] = frozenset(
    {
        "gpt-5",
        "gpt-5-2025-08-07",
        "gpt-5-codex",
        "gpt-5-mini",
        "gpt-5-mini-2025-08-07",
        "gpt-5-nano",
        "gpt-5-nano-2025-08-07",
        "gpt-5-pro",
        "gpt-5-pro-2025-10-06",
        "gpt-5.1",
        "gpt-5.1-2025-11-13",
        "gpt-5.1-codex",
        "gpt-5.1-codex-max",
        "gpt-5.1-codex-mini",
        "gpt-5.2",
        "gpt-5.2-2025-12-11",
        "gpt-5.2-codex",
        "gpt-5.2-pro",
        "gpt-5.2-pro-2025-12-11",
        "gpt-5.3-codex",
        "gpt-5.4",
        "gpt-5.4-2026-03-05",
        "gpt-5.4-mini",
        "gpt-5.4-mini-2026-03-17",
        "gpt-5.4-nano",
        "gpt-5.4-nano-2026-03-17",
        "gpt-5.4-pro",
        "gpt-5.4-pro-2026-03-05",
        "gpt-5.5",
        "gpt-5.5-2026-04-23",
        "gpt-5.5-pro",
        "gpt-5.5-pro-2026-04-23",
        "o1",
        "o1-2024-12-17",
        "o1-pro",
        "o1-pro-2025-03-19",
        "o3",
        "o3-2025-04-16",
        "o3-mini",
        "o3-mini-2025-01-31",
        "o4-mini",
        "o4-mini-2025-04-16",
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
        start_time = time.perf_counter()
        logger.debug("LLM request: OpenAI model '%s'", model)
        try:
            response = await self.client.responses.create(
                model=model,
                input=input_data,
                **kwargs,
            )
        except Exception:
            duration = time.perf_counter() - start_time
            logger.debug("LLM request failed: OpenAI model '%s' in %.3f seconds", model, duration)
            raise

        duration = time.perf_counter() - start_time
        logger.debug("LLM response: OpenAI model '%s' completed in %.3f seconds", model, duration)
        output_text = response.output_text
        if not output_text:
            raise RuntimeError(f"Model '{model}' returned an empty response.")
        return str(output_text)

    async def close(self):
        await self.client.close()


class AzureOpenAIClient(OpenAIClient):
    def __init__(
        self,
        api_key: str | None,
        azure_endpoint: str,
        api_version: str,
        deployment_mapping: dict[str, str] | None = None,
        azure_ad_token_provider: AsyncAzureADTokenProvider | None = None,
        credential: AsyncTokenCredential | None = None,
        timeout: float | Timeout | NotGiven | None = NOT_GIVEN,
        max_retries: int = DEFAULT_MAX_RETRIES,
        _strict_response_validation: bool = False,
    ):
        self.client = AsyncAzureOpenAI(
            api_key=api_key,
            azure_ad_token_provider=azure_ad_token_provider,
            azure_endpoint=azure_endpoint,
            api_version=api_version,
            timeout=timeout,
            max_retries=max_retries,
            _strict_response_validation=_strict_response_validation,
        )
        self.credential = credential
        self.deployment_mapping = deployment_mapping or {}

    async def query_llm(
        self,
        model: str,
        messages: list[Message],
        **kwargs: Any,
    ) -> str:
        canonical_model = self.deployment_mapping.get(model, model)
        input_messages = cast(ResponseInputParam, [message.model_dump() for message in messages])
        kwargs.pop("deployment_mapping", None)

        if canonical_model in CHAT_MODELS:
            return await self._query_chat_model(model, input_messages)

        if canonical_model in REASONING_MODELS:
            return await self._query_reasoning_model(
                model=model,
                input_messages=input_messages,
                reasoning_effort=kwargs.get("reasoning_effort", "medium"),
            )

        return await self._query_fallback_model(model, input_messages, **kwargs)

    async def close(self):
        await self.client.close()
        if self.credential is not None:
            await self.credential.close()
