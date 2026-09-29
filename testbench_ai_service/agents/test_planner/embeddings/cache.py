"""File cache for embeddings, one ``.npy`` file per content hash."""

import hashlib
import os
import re
from collections import Counter
from pathlib import Path

import numpy as np

from testbench_ai_service.agents.test_planner.embeddings.base import EmbeddingClient
from testbench_ai_service.log import logger


class EmbeddingCache:
    def __init__(self, cache_dir: Path, provider: str, model: str):
        self.provider = provider
        self.model = model
        self.root = Path(cache_dir) / provider / re.sub(r"[^A-Za-z0-9._-]+", "_", model)

    def key(self, text: str) -> str:
        return hashlib.sha256(f"{self.provider}\0{self.model}\0{text}".encode()).hexdigest()

    def path_for(self, text: str) -> Path:
        digest = self.key(text)
        return self.root / digest[:2] / f"{digest}.npy"

    def get(self, text: str) -> np.ndarray | None:
        path = self.path_for(text)
        if not path.is_file():
            return None
        try:
            vector = np.load(path, allow_pickle=False)
        except (OSError, ValueError) as e:
            logger.warning("Discarding unreadable cached embedding '%s': %s", path, e)
            path.unlink(missing_ok=True)
            return None
        if vector.ndim != 1:
            logger.warning("Discarding malformed cached embedding '%s'", path)
            path.unlink(missing_ok=True)
            return None
        return vector.astype(np.float32, copy=False)

    def put(self, text: str, vector: np.ndarray) -> None:
        path = self.path_for(text)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(".tmp")
        with temp_path.open("wb") as file:
            np.save(file, np.asarray(vector, dtype=np.float32), allow_pickle=False)
        os.replace(temp_path, path)


async def embed_with_cache(
    client: EmbeddingClient, cache: EmbeddingCache, texts: list[str], batch_size: int
) -> np.ndarray:
    """
    Embed ``texts``, reading from and writing to ``cache``.

    Only texts missing from the cache go to the client, ``batch_size`` at a
    time. Cached vectors whose dimension differs from the rest (e.g. from an
    older model) are discarded and recomputed.

    Returns:
        A float32 matrix with one row per text.
    """
    if not texts:
        return np.empty((0, 0), dtype=np.float32)

    vectors: list[np.ndarray | None] = [cache.get(text) for text in texts]
    missing = [index for index, vector in enumerate(vectors) if vector is None]
    await _fill(client, cache, texts, vectors, missing, batch_size)

    filled = [vector for vector in vectors if vector is not None]
    if missing:
        expected = vectors[missing[0]].shape[0]  # type: ignore[union-attr]
    else:
        expected = Counter(vector.shape[0] for vector in filled).most_common(1)[0][0]
    stale = [index for index, vector in enumerate(vectors) if vector.shape[0] != expected]  # type: ignore[union-attr]
    if stale:
        logger.warning("Recomputing %d cached embeddings with another dimension", len(stale))
        await _fill(client, cache, texts, vectors, stale, batch_size)

    return np.vstack(vectors)  # type: ignore[arg-type]


async def _fill(
    client: EmbeddingClient,
    cache: EmbeddingCache,
    texts: list[str],
    vectors: list[np.ndarray | None],
    indices: list[int],
    batch_size: int,
) -> None:
    for start in range(0, len(indices), batch_size):
        batch = indices[start : start + batch_size]
        result = await client.embed([texts[index] for index in batch])
        if len(result) != len(batch):
            raise ValueError(
                f"Embedding client returned {len(result)} vectors for {len(batch)} texts"
            )
        for index, vector in zip(batch, result, strict=True):
            vectors[index] = vector
            cache.put(texts[index], vector)
