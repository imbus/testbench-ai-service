import importlib.util
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from testbench_ai_service.agents.test_planner.embeddings.factory import create_embedding_client
from testbench_ai_service.agents.test_planner.embeddings.openai import OpenAIEmbeddingClient
from testbench_ai_service.agents.test_planner.model import EmbeddingArgs
from testbench_ai_service.llm.base import AzureAuthMethod, LLMProvider
from testbench_ai_service.models.config import LLMConfig

_FACTORY = "testbench_ai_service.agents.test_planner.embeddings.factory"


def _sdk_client(vectors_by_index):
    client = MagicMock()
    client.embeddings.create = AsyncMock(
        return_value=SimpleNamespace(
            data=[SimpleNamespace(index=i, embedding=v) for i, v in vectors_by_index]
        )
    )
    client.close = AsyncMock()
    return client


async def test_openai_client_orders_by_index():
    sdk = _sdk_client([(1, [0.0, 1.0]), (0, [1.0, 0.0])])
    client = OpenAIEmbeddingClient("m", sdk)

    vectors = await client.embed(["a", "b"])

    sdk.embeddings.create.assert_awaited_once_with(model="m", input=["a", "b"])
    assert vectors.dtype == np.float32
    assert np.array_equal(vectors, [[1.0, 0.0], [0.0, 1.0]])


async def test_close_closes_sdk_client_and_credential():
    sdk = _sdk_client([])
    credential = MagicMock(close=AsyncMock())

    await OpenAIEmbeddingClient("m", sdk, credential=credential).close()

    sdk.close.assert_awaited_once()
    credential.close.assert_awaited_once()


def test_factory_openai_uses_resolved_key():
    with (
        patch(f"{_FACTORY}.resolve_credential", return_value="key") as resolve,
        patch(f"{_FACTORY}.AsyncOpenAI") as sdk,
    ):
        client = create_embedding_client(EmbeddingArgs(), LLMConfig(), "P")

    resolve.assert_called_once_with(LLMProvider.OPENAI, LLMConfig(), "P")
    sdk.assert_called_once_with(api_key="key")
    assert isinstance(client, OpenAIEmbeddingClient)


def test_factory_azure_with_api_key():
    config = LLMConfig(
        provider=LLMProvider.AZURE_OPENAI, azure_endpoint="https://x", api_version="v"
    )
    with (
        patch(f"{_FACTORY}.resolve_credential", return_value="key"),
        patch(f"{_FACTORY}.AsyncAzureOpenAI") as sdk,
    ):
        create_embedding_client(EmbeddingArgs(provider="azure_openai", model="dep"), config, "P")

    sdk.assert_called_once_with(api_key="key", azure_endpoint="https://x", api_version="v")


def test_factory_azure_with_entra_id():
    from testbench_ai_service.llm.azure_auth import EntraIdCredentials

    config = LLMConfig(
        provider=LLMProvider.AZURE_OPENAI,
        auth_method=AzureAuthMethod.ENTRA_ID,
        azure_endpoint="https://x",
        api_version="v",
    )
    entra = EntraIdCredentials(tenant_id="t", client_id="c", client_secret="s")
    with (
        patch(f"{_FACTORY}.resolve_credential", return_value=entra),
        patch(f"{_FACTORY}.create_token_provider", return_value=("cred", "provider")),
        patch(f"{_FACTORY}.AsyncAzureOpenAI") as sdk,
    ):
        client = create_embedding_client(EmbeddingArgs(provider="azure_openai"), config, "P")

    sdk.assert_called_once_with(
        azure_ad_token_provider="provider", azure_endpoint="https://x", api_version="v"
    )
    assert client.credential == "cred"


def test_factory_azure_needs_endpoint_in_llm_config():
    with pytest.raises(ValueError, match="azure_endpoint"):
        create_embedding_client(EmbeddingArgs(provider="azure_openai"), LLMConfig(), "P")


def test_factory_local_builds_fastembed_client():
    with patch("importlib.util.find_spec", return_value=object()):
        args = EmbeddingArgs(provider="local", model="BAAI/bge-small-en-v1.5")
    with patch(f"{_FACTORY}.FastEmbedClient") as local:
        create_embedding_client(args, LLMConfig(), "P")

    local.assert_called_once_with("BAAI/bge-small-en-v1.5")


@pytest.mark.skipif(importlib.util.find_spec("fastembed") is None, reason="fastembed not installed")
async def test_fastembed_client_embeds():
    from testbench_ai_service.agents.test_planner.embeddings.local import FastEmbedClient

    vectors = await FastEmbedClient("BAAI/bge-small-en-v1.5").embed(["hello", "world"])

    assert vectors.shape[0] == 2
    assert vectors.dtype == np.float32
