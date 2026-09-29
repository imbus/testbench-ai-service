import hashlib

import numpy as np
import pytest

from testbench_ai_service.agents.test_planner.embeddings.base import EmbeddingClient
from testbench_ai_service.agents.test_planner.embeddings.cache import (
    EmbeddingCache,
    embed_with_cache,
)


class FakeClient(EmbeddingClient):
    def __init__(self, dimension=4):
        self.dimension = dimension
        self.calls: list[list[str]] = []

    async def embed(self, texts):
        self.calls.append(list(texts))
        return np.array(
            [
                np.frombuffer(hashlib.sha256(t.encode()).digest()[: self.dimension], np.uint8)
                for t in texts
            ],
            dtype=np.float32,
        )


@pytest.fixture
def cache(tmp_path):
    return EmbeddingCache(tmp_path, "openai", "text-embedding-3-small")


async def test_embeds_in_batches_and_keeps_order(cache):
    client = FakeClient()
    texts = ["a", "b", "c"]

    vectors = await embed_with_cache(client, cache, texts, batch_size=2)

    assert client.calls == [["a", "b"], ["c"]]
    assert vectors.shape == (3, 4)
    assert np.array_equal(vectors[2], (await FakeClient().embed(["c"]))[0])


async def test_second_run_hits_the_cache(cache):
    await embed_with_cache(FakeClient(), cache, ["a", "b"], batch_size=10)
    client = FakeClient()

    await embed_with_cache(client, cache, ["a", "b", "c"], batch_size=10)

    assert client.calls == [["c"]]


async def test_cache_key_includes_the_model(tmp_path):
    await embed_with_cache(FakeClient(), EmbeddingCache(tmp_path, "openai", "m1"), ["a"], 10)
    client = FakeClient()

    await embed_with_cache(client, EmbeddingCache(tmp_path, "openai", "m2"), ["a"], 10)

    assert client.calls == [["a"]]


async def test_broken_cache_file_is_recomputed(cache, caplog):
    await embed_with_cache(FakeClient(), cache, ["a"], 10)
    cache.path_for("a").write_bytes(b"not a numpy file")
    client = FakeClient()

    await embed_with_cache(client, cache, ["a"], 10)

    assert client.calls == [["a"]]
    assert "Discarding unreadable cached embedding" in caplog.text


async def test_cached_vector_with_other_dimension_is_recomputed(cache):
    await embed_with_cache(FakeClient(dimension=4), cache, ["old"], 10)
    client = FakeClient(dimension=8)

    vectors = await embed_with_cache(client, cache, ["old", "new"], 10)

    assert vectors.shape == (2, 8)
    assert client.calls == [["new"], ["old"]]


async def test_no_texts_gives_empty_matrix(cache):
    assert (await embed_with_cache(FakeClient(), cache, [], 10)).shape == (0, 0)


async def test_wrong_number_of_vectors_raises(cache):
    class ShortClient(FakeClient):
        async def embed(self, texts):
            return (await super().embed(texts))[:-1]

    with pytest.raises(ValueError, match="returned 1 vectors for 2 texts"):
        await embed_with_cache(ShortClient(), cache, ["a", "b"], 10)
