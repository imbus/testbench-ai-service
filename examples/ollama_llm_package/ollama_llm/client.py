from __future__ import annotations

import os

import httpx

from testbench_ai_service.llm.base import LLMClient, LLMResult, TokenUsage, token_count
from testbench_ai_service.models.prompt import Message

DEFAULT_PORT = 11434
DEFAULT_HOST = f"http://localhost:{DEFAULT_PORT}"

DEFAULT_TIMEOUT = 300

THINK_LEVELS = ("low", "medium", "high")


class OllamaError(RuntimeError):
    """Ollama refused the request or answered with something unusable."""


def base_url(host: str | None) -> str:
    """The URL of the Ollama server for a value of ``OLLAMA_HOST``.

    Ollama accepts ``host``, ``host:port`` and full URLs there; a missing
    scheme means http and a missing port the default one.
    """
    value = (host or "").strip().rstrip("/")
    if not value:
        return DEFAULT_HOST
    if "://" not in value:
        value = f"http://{value}"
    url = httpx.URL(value)
    if url.port is None and url.scheme == "http":
        url = url.copy_with(port=DEFAULT_PORT)
    return str(url).rstrip("/")


def _num_ctx(value: str | None) -> int | None:
    if value is None or not value.strip():
        return None
    try:
        number = int(value)
    except ValueError:
        raise OllamaError(f"OLLAMA_NUM_CTX must be a whole number, got '{value}'") from None
    if number <= 0:
        raise OllamaError(f"OLLAMA_NUM_CTX must be positive, got '{value}'")
    return number


def _think(value: str | None) -> bool | str | None:
    """The ``think`` setting of a chat request for a value of ``OLLAMA_THINK``."""
    setting = (value or "").strip().lower()
    if not setting:
        return None
    if setting in ("true", "false"):
        return setting == "true"
    if setting in THINK_LEVELS:
        return setting
    raise OllamaError(
        f"OLLAMA_THINK must be true, false or one of {', '.join(THINK_LEVELS)}, got '{value}'"
    )


class OllamaLLMClient(LLMClient):
    def __init__(
        self,
        api_key: str | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        **kwargs,
    ):
        key = api_key or os.getenv("OLLAMA_API_KEY")
        self.num_ctx = _num_ctx(os.getenv("OLLAMA_NUM_CTX"))
        self.keep_alive = os.getenv("OLLAMA_KEEP_ALIVE") or None
        self.think = _think(os.getenv("OLLAMA_THINK"))
        self.base_url = base_url(os.getenv("OLLAMA_HOST"))
        self.http = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {key}"} if key else {},
            timeout=kwargs.get("timeout") or DEFAULT_TIMEOUT,
            # Retries a connection that could not be opened, not a failed answer.
            transport=transport
            or httpx.AsyncHTTPTransport(retries=int(kwargs.get("max_retries") or 0)),
        )

    def _payload(self, model: str, messages: list[Message]) -> dict:
        payload: dict = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            # One JSON answer instead of a stream of tokens.
            "stream": False,
        }
        if self.num_ctx is not None:
            payload["options"] = {"num_ctx": self.num_ctx}
        if self.keep_alive is not None:
            payload["keep_alive"] = self.keep_alive
        if self.think is not None:
            payload["think"] = self.think
        return payload

    async def query_llm_with_usage(
        self, model: str, messages: list[Message], *args, **kwargs
    ) -> LLMResult:
        try:
            response = await self.http.post("/api/chat", json=self._payload(model, messages))
        except httpx.ConnectError as error:
            raise OllamaError(
                f"Cannot reach Ollama at {self.base_url}. Is it running, and is OLLAMA_HOST "
                f"set in the environment of the service? ({error})"
            ) from error
        except httpx.TimeoutException as error:
            raise OllamaError(
                f"Ollama at {self.base_url} did not answer in time for model '{model}'. "
                "Raise llm_config.timeout; a large model takes a while to load."
            ) from error

        try:
            body = response.json()
        except ValueError:
            body = None
        if response.is_error:
            # Ollama names the reason, e.g. "model 'x' not found", in "error".
            reason = body.get("error") if isinstance(body, dict) else None
            raise OllamaError(
                f"Ollama answered {response.status_code} for model '{model}': "
                f"{reason or response.text[:200]}"
            )
        message = body.get("message") if isinstance(body, dict) else None
        text = message.get("content") if isinstance(message, dict) else None
        if not isinstance(text, str):
            raise OllamaError(f"Ollama returned no message content for model '{model}'")
        if not text.strip() and body.get("done_reason") == "length":
            # A thinking model reasons in "thinking" first; the answer never started.
            spent = (
                "spent all of them on thinking" if message.get("thinking") else "produced no answer"
            )
            raise OllamaError(
                f"Model '{model}' ran out of tokens and {spent}. Raise OLLAMA_NUM_CTX "
                "(the context window holds the prompt, the thinking and the answer) "
                "or set OLLAMA_THINK=false."
            )

        # Both counts are left out when Ollama answers from its prompt cache.
        prompt, generated = (
            token_count(body.get("prompt_eval_count")),
            token_count(body.get("eval_count")),
        )
        usage = (
            TokenUsage(input_tokens=prompt or 0, output_tokens=generated or 0)
            if prompt is not None or generated is not None
            else None
        )
        return LLMResult(text=text, usage=usage)

    async def query_llm(self, model: str, messages: list[Message], *args, **kwargs) -> str:
        return (await self.query_llm_with_usage(model, messages, *args, **kwargs)).text

    async def close(self):
        await self.http.aclose()
