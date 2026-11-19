"""An LLM client for an OpenAI-compatible chat completions API.

Upload the built wheel in the console's LLM screen and use it as the LLM
provider. The base URL and the API key come from the environment of the
service, because the console does not manage credentials of custom clients:

    ACME_LLM_BASE_URL   e.g. https://llm.example.com/v1
    ACME_LLM_API_KEY    optional
"""

from __future__ import annotations

import os

import httpx

from testbench_ai_service.llm.base import LLMClient
from testbench_ai_service.models.prompt import Message

DEFAULT_BASE_URL = "http://localhost:11434/v1"


class AcmeLLMClient(LLMClient):
    def __init__(self, api_key: str | None = None, **kwargs):
        # The service passes api_key=None for custom clients, plus 'timeout' and
        # 'max_retries' when they are set in llm_config. Accept **kwargs so a
        # setting added later does not break the constructor.
        key = api_key or os.getenv("ACME_LLM_API_KEY")
        self.http = httpx.AsyncClient(
            base_url=os.getenv("ACME_LLM_BASE_URL", DEFAULT_BASE_URL),
            headers={"Authorization": f"Bearer {key}"} if key else {},
            timeout=kwargs.get("timeout") or 60,
        )

    async def query_llm(self, model: str, messages: list[Message], *args, **kwargs) -> str:
        payload = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        response = await self.http.post("/chat/completions", json=payload)
        response.raise_for_status()
        content: str = response.json()["choices"][0]["message"]["content"]
        return content

    async def close(self):
        await self.http.aclose()
