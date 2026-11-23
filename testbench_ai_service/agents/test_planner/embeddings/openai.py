from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from openai import AsyncOpenAI

from testbench_ai_service.agents.test_planner.embeddings.base import EmbeddingClient

if TYPE_CHECKING:
    from azure.core.credentials_async import AsyncTokenCredential


class OpenAIEmbeddingClient(EmbeddingClient):
    """Embeddings via the OpenAI API; ``client`` may also be an ``AsyncAzureOpenAI``."""

    def __init__(
        self, model: str, client: AsyncOpenAI, credential: AsyncTokenCredential | None = None
    ):
        self.model = model
        self.client = client
        self.credential = credential

    async def embed(self, texts: list[str]) -> np.ndarray:
        response = await self.client.embeddings.create(model=self.model, input=texts)
        rows = sorted(response.data, key=lambda item: item.index)
        return np.asarray([row.embedding for row in rows], dtype=np.float32)

    async def close(self) -> None:
        await self.client.close()
        if self.credential is not None:
            await self.credential.close()
