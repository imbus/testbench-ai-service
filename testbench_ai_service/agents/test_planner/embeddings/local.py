import asyncio
from typing import Any

import numpy as np

from testbench_ai_service.agents.test_planner.embeddings.base import EmbeddingClient


class FastEmbedClient(EmbeddingClient):
    """In-process embeddings with fastembed (ONNX, optional extra ``local-embeddings``).

    The model is loaded on first use; fastembed downloads it into its cache
    if it is not there yet.
    """

    def __init__(self, model: str):
        self.model_name = model
        self._model: Any = None

    def _embed_sync(self, texts: list[str]) -> np.ndarray:
        if self._model is None:
            # fastembed is optional (extra 'local-embeddings'); import on first use only
            from fastembed import TextEmbedding  # noqa: PLC0415

            self._model = TextEmbedding(model_name=self.model_name)
        return np.asarray(list(self._model.embed(texts)), dtype=np.float32)

    async def embed(self, texts: list[str]) -> np.ndarray:
        return await asyncio.to_thread(self._embed_sync, texts)
