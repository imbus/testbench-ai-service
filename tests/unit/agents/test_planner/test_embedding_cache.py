import hashlib
from unittest.mock import patch

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


async def test_failing_cache_write_does_not_abort_the_run(cache, caplog):
    with patch("pathlib.Path.replace", side_effect=PermissionError("locked")):
        vectors = await embed_with_cache(FakeClient(), cache, ["a", "b"], 10)

    assert vectors.shape == (2, 4)
    assert "Could not cache embedding" in caplog.text
    assert cache.get("a") is None


async def test_write_does_not_collide_with_another_writers_temp_file(cache):
    # a fixed '<hash>.tmp' name would clash with a concurrent writer
    blocker = cache.path_for("a").with_suffix(".tmp")
    blocker.mkdir(parents=True)

    await embed_with_cache(FakeClient(), cache, ["a"], 10)

    assert cache.get("a") is not None


async def test_failing_discard_of_a_broken_file_is_ignored(cache):
    await embed_with_cache(FakeClient(), cache, ["a"], 10)
    cache.path_for("a").write_bytes(b"broken")

    with patch("pathlib.Path.unlink", side_effect=PermissionError("locked")):
        assert cache.get("a") is None


async def test_mixed_cached_dimensions_without_missing_texts(cache):
    for text in ["a", "b", "c"]:
        cache.put(text, np.ones(4, dtype=np.float32))
    cache.put("d", np.ones(8, dtype=np.float32))
    client = FakeClient(dimension=8)

    vectors = await embed_with_cache(client, cache, ["a", "b", "c", "d"], 10)

    assert vectors.shape == (4, 8)


async def test_client_with_inconsistent_dimensions_raises_a_clear_error(cache):
    class WobblyClient(FakeClient):
        async def embed(self, texts):
            self.calls.append(list(texts))
            return np.ones((len(texts), 4 + len(self.calls)), dtype=np.float32)

    cache.put("a", np.ones(3, dtype=np.float32))

    with pytest.raises(ValueError, match="different dimensions"):
        await embed_with_cache(WobblyClient(), cache, ["a", "b"], 1)
