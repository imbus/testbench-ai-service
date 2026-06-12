from __future__ import annotations

from typing import Any

from anthropic import DEFAULT_MAX_RETRIES, NOT_GIVEN, AsyncAnthropic, NotGiven
from anthropic.types import MessageParam
from httpx import Timeout

from testbench_ai_service.llm.base import LLMClient
from testbench_ai_service.log import logger
from testbench_ai_service.models.prompt import Message

BUDGET_THINKING_MODELS: frozenset[str] = frozenset(
    {
        "claude-haiku-4-5",
        "claude-haiku-4-5-20251001",
        "claude-opus-4-1",
        "claude-opus-4-1-20250805",
        "claude-opus-4-5",
        "claude-opus-4-5-20251101",
        "claude-sonnet-4-5",
        "claude-sonnet-4-5-20250929",
    }
)

ADAPTIVE_THINKING_MODELS: frozenset[str] = frozenset(
    {
        "claude-opus-4-6",
        "claude-opus-4-7",
        "claude-opus-4-8",
        "claude-sonnet-4-6",
    }
)


class AnthropicClient(LLMClient):
    def __init__(
        self,
        api_key: str | None,
        timeout: float | Timeout | NotGiven | None = NOT_GIVEN,
        max_retries: int = DEFAULT_MAX_RETRIES,
        _strict_response_validation: bool = False,
    ):
        self.client = AsyncAnthropic(
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
        system_prompt = next((msg.content for msg in messages if msg.role == "system"), NOT_GIVEN)

        anthropic_messages: list[MessageParam] = [
            {"role": msg.role, "content": msg.content} for msg in messages if msg.role != "system"
        ]

        if model in BUDGET_THINKING_MODELS:
            return await self._query_budget_thinking_model(
                model=model,
                input_messages=anthropic_messages,
                system_prompt=system_prompt,
                reasoning_effort=kwargs.get("reasoning_effort", "medium"),
                **kwargs,
            )

        if model in ADAPTIVE_THINKING_MODELS:
            return await self._query_adaptive_thinking_model(
                model=model,
                input_messages=anthropic_messages,
                system_prompt=system_prompt,
                reasoning_effort=kwargs.get("reasoning_effort", "high"),
                **kwargs,
            )

        return await self._query_fallback_model(model, anthropic_messages, system_prompt, **kwargs)

    async def _query_budget_thinking_model(
        self,
        model: str,
        input_messages: list[MessageParam],
        system_prompt: str | NotGiven,
        reasoning_effort: str,
        **kwargs: Any,
    ) -> str:
        effort_to_budget = {"low": 2048, "medium": 4096, "high": 8192}
        budget_tokens = effort_to_budget.get(reasoning_effort, 4096)

        max_tokens = kwargs.get("max_tokens", 8192)
        if max_tokens <= budget_tokens:
            max_tokens = budget_tokens + 1024

        kwargs.pop("temperature", None)

        return await self._create_response(
            model=model,
            messages=input_messages,
            system=system_prompt,
            thinking={"type": "enabled", "budget_tokens": budget_tokens},
            max_tokens=max_tokens,
            **kwargs,
        )

    async def _query_adaptive_thinking_model(
        self,
        model: str,
        input_messages: list[MessageParam],
        system_prompt: str | NotGiven,
        reasoning_effort: str,
        **kwargs: Any,
    ) -> str:
        valid_efforts = {"low", "medium", "high", "xhigh", "max"}
        effort = reasoning_effort if reasoning_effort in valid_efforts else "high"

        max_tokens = kwargs.pop("max_tokens", 16000)
        kwargs.pop("temperature", None)

        return await self._create_response(
            model=model,
            messages=input_messages,
            system=system_prompt,
            thinking={"type": "adaptive"},
            output_config={"effort": effort},
            max_tokens=max_tokens,
            **kwargs,
        )

    async def _query_fallback_model(
        self,
        model: str,
        input_messages: list[MessageParam],
        system_prompt: str | NotGiven,
        **kwargs: Any,
    ) -> str:
        logger.warning(
            "Model '%s' is not explicitly supported. Attempting a fallback request.", model
        )
        try:
            return await self._create_response(
                model=model,
                messages=input_messages,
                system=system_prompt,
                **kwargs,
            )
        except Exception as e:
            raise RuntimeError(f"Fallback request failed for model '{model}': {e}") from e

    async def _create_response(
        self, model: str, messages: list[MessageParam], **kwargs: Any
    ) -> str:
        if "max_tokens" not in kwargs and "thinking" not in kwargs:
            kwargs["max_tokens"] = 4096

        response = await self.client.messages.create(
            model=model,
            messages=messages,
            **kwargs,
        )

        for block in response.content:
            if block.type == "text":
                return str(block.text)

        raise RuntimeError(f"Model '{model}' returned an empty or non-text response.")

    async def close(self):
        await self.client.close()
