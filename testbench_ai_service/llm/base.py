from abc import ABC, abstractmethod
from enum import Enum

from testbench_ai_service.models.prompt import Message


class LLMProvider(str, Enum):
    OPENAI = "openai"
    AZURE_OPENAI = "azure_openai"
    CUSTOM = "custom"

    def __str__(self):
        return self.value


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

    @abstractmethod
    async def close(self):
        """
        Close the client and release any allocated resources or connections.
        """
