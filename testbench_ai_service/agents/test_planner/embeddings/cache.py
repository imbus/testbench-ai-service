"""File cache for embeddings, one ``.npy`` file per content hash.

The cache is an optimisation: a file that cannot be read, written or removed
(locked by another process, virus scanner, missing permissions) only costs a
recomputation and a warning, never the run.
"""

import asyncio
import contextlib
import hashlib
import os
import re
import tempfile
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
            _discard(path)
            return None
        if vector.ndim != 1:
            logger.warning("Discarding malformed cached embedding '%s'", path)
            _discard(path)
            return None
        return vector.astype(np.float32, copy=False)

    def put(self, text: str, vector: np.ndarray) -> None:
        path = self.path_for(text)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            # A unique temp file per write, so concurrent writers of the same
            # text never share one; os.replace makes the final step atomic.
            handle, temp_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
            temp_path = Path(temp_name)
            try:
                with os.fdopen(handle, "wb") as file:
                    np.save(file, np.asarray(vector, dtype=np.float32), allow_pickle=False)
                temp_path.replace(path)
            finally:
                _discard(temp_path)
        except OSError as e:
            logger.warning("Could not cache embedding '%s': %s", path, e)


def _discard(path: Path) -> None:
    with contextlib.suppress(OSError):
        path.unlink(missing_ok=True)


async def embed_with_cache(
    client: EmbeddingClient, cache: EmbeddingCache, texts: list[str], batch_size: int
) -> np.ndarray:
    """
    Embed ``texts``, reading from and writing to ``cache``.

    Only texts missing from the cache go to the client, ``batch_size`` at a
    time. Cached vectors whose dimension differs from what the client returns
    now (e.g. from an older model behind the same name) are recomputed. File
    access runs in a worker thread so the event loop stays responsive.

    Returns:
        A float32 matrix with one row per text.

    Raises:
        ValueError: If the client itself returns vectors of different dimensions.
    """
    if not texts:
        return np.empty((0, 0), dtype=np.float32)

    vectors: list[np.ndarray | None] = await asyncio.to_thread(_load, cache, texts)
    missing = [index for index, vector in enumerate(vectors) if vector is None]
    await _fill(client, cache, texts, vectors, missing, batch_size)

    if len({vector.shape[0] for vector in vectors if vector is not None}) > 1:
        if missing:
            expected = vectors[missing[0]].shape[0]  # type: ignore[union-attr]
        else:
            # Everything came from the cache: ask the client for the dimension it uses now.
            expected = (await client.embed([texts[0]])).shape[1]
        stale = [
            index
            for index, vector in enumerate(vectors)
            if vector is not None and vector.shape[0] != expected
        ]
        logger.warning("Recomputing %d cached embeddings with another dimension", len(stale))
        await _fill(client, cache, texts, vectors, stale, batch_size)
        if len({vector.shape[0] for vector in vectors if vector is not None}) > 1:
            raise ValueError("Embedding client returned vectors of different dimensions")

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
        await asyncio.to_thread(
            _store,
            cache,
            [(texts[index], vector) for index, vector in zip(batch, result, strict=True)],
        )


def _load(cache: EmbeddingCache, texts: list[str]) -> list[np.ndarray | None]:
    return [cache.get(text) for text in texts]


def _store(cache: EmbeddingCache, items: list[tuple[str, np.ndarray]]) -> None:
    for text, vector in items:
        cache.put(text, vector)
