from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

from testbench_ai_service.models.prompt import Message


class LLMProvider(str, Enum):
    OPENAI = "openai"
    AZURE_OPENAI = "azure_openai"
    ANTHROPIC = "anthropic"
    CUSTOM = "custom"

    def __str__(self):
        return self.value


class AzureAuthMethod(str, Enum):
    API_KEY = "api_key"
    ENTRA_ID = "entra_id"

    def __str__(self):
        return self.value


class RoutingFamily(str, Enum):
    """How a client shapes the request for a given model.

    Lives in ``base`` rather than in ``routing`` so the clients can name a
    family without importing ``routing``, which imports them back.
    """

    CHAT = "chat"
    REASONING = "reasoning"
    ADAPTIVE = "adaptive"
    BUDGET = "budget"
    FALLBACK = "fallback"

    def __str__(self):
        return self.value


@dataclass(frozen=True)
class TokenUsage:
    """What one call consumed, as the provider reported it.

    ``input_tokens`` counts every prompt token, cached or not -- Anthropic
    reports cache reads and writes separately, and they are summed here so
    both providers mean the same thing. ``reasoning_tokens`` is a subset of
    ``output_tokens`` for both providers, and ``None`` when not reported.
    """

    input_tokens: int
    output_tokens: int
    reasoning_tokens: int | None = None


@dataclass(frozen=True)
class LLMResult:
    """The response text plus its usage, ``None`` when the provider gave none."""

    text: str
    usage: TokenUsage | None = None


def token_count(value: object) -> int | None:
    """*value* if it is a token count, else ``None``.

    Usage objects come from the SDKs, but an OpenAI-compatible endpoint or an
    older API version may leave a field out; a missing count must read as
    "not reported", never as an error after the call already succeeded.
    """
    return value if isinstance(value, int) and not isinstance(value, bool) else None


class LLMClient(ABC):
    @abstractmethod
    def __init__(self, api_key: str | None = None, *args, **kwargs):
        """
        Initialize the client with optional API key and other provider-specific params.

        Args:
            api_key: API key or None if authentication is not required.
            *args: Additional positional arguments.
            **kwargs: Provider-specific keyword arguments.
        """

    @abstractmethod
    async def query_llm(self, model: str, messages: list[Message], *args, **kwargs) -> str:
        """
        Send a query to the LLM and return the generated response.

        Args:
            model: The model identifier to use for the query.
            messages: A list of messages, e.g., [Message(role="user", content="Hello")].
            *args: Additional positional arguments.
            **kwargs: Provider-specific keyword arguments.

        Returns:
            Response text from the LLM.
        """

    async def query_llm_with_usage(
        self, model: str, messages: list[Message], *args, **kwargs
    ) -> LLMResult:
        """
        Like ``query_llm``, but also return the token usage of the call.

        The default reports no usage, so a custom client that implements only
        ``query_llm`` keeps working. The built-in clients override this.
        """
        return LLMResult(text=await self.query_llm(model, messages, *args, **kwargs))

    @abstractmethod
    async def close(self):
        """
        Close the client and release any allocated resources or connections.
        """
