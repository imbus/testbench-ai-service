from openai import AsyncAzureOpenAI, AsyncOpenAI

from testbench_ai_service.agents.test_planner.embeddings.base import EmbeddingClient
from testbench_ai_service.agents.test_planner.embeddings.local import FastEmbedClient
from testbench_ai_service.agents.test_planner.embeddings.openai import OpenAIEmbeddingClient
from testbench_ai_service.agents.test_planner.model import EmbeddingArgs, EmbeddingProvider
from testbench_ai_service.llm.azure_auth import EntraIdCredentials, create_token_provider
from testbench_ai_service.llm.base import LLMProvider
from testbench_ai_service.llm.credentials import resolve_credential
from testbench_ai_service.models.config import LLMConfig


def create_embedding_client(
    args: EmbeddingArgs, llm_config: LLMConfig, project_name: str
) -> EmbeddingClient:
    """
    Build the embedding client configured in ``args``.

    OpenAI and Azure use the same credentials as the LLM clients of the project;
    Azure also takes ``azure_endpoint``, ``api_version`` and ``auth_method`` from
    the resolved LLM config.
    """
    if args.provider == EmbeddingProvider.LOCAL:
        return FastEmbedClient(args.model)

    if args.provider == EmbeddingProvider.OPENAI:
        credential = resolve_credential(LLMProvider.OPENAI, llm_config, project_name)
        if isinstance(credential, EntraIdCredentials):
            raise ValueError("Entra ID credentials are only supported for provider 'azure_openai'.")
        return OpenAIEmbeddingClient(args.model, AsyncOpenAI(api_key=credential))

    if not llm_config.azure_endpoint or not llm_config.api_version:
        raise ValueError(
            "Embedding provider 'azure_openai' needs 'azure_endpoint' and 'api_version' "
            "in the llm_config."
        )
    credential = resolve_credential(LLMProvider.AZURE_OPENAI, llm_config, project_name)
    if isinstance(credential, EntraIdCredentials):
        azure_credential, token_provider = create_token_provider(credential)
        client = AsyncAzureOpenAI(
            azure_ad_token_provider=token_provider,
            azure_endpoint=llm_config.azure_endpoint,
            api_version=llm_config.api_version,
        )
        return OpenAIEmbeddingClient(args.model, client, credential=azure_credential)
    client = AsyncAzureOpenAI(
        api_key=credential,
        azure_endpoint=llm_config.azure_endpoint,
        api_version=llm_config.api_version,
    )
    return OpenAIEmbeddingClient(args.model, client)
