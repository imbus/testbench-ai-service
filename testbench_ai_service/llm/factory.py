import os
import re
from typing import Any

from testbench_ai_service.config import LLMConfig
from testbench_ai_service.llm.anthropic import AnthropicClient
from testbench_ai_service.llm.base import LLMClient, LLMProvider
from testbench_ai_service.llm.openai import AzureOpenAIClient, OpenAIClient
from testbench_ai_service.utils.import_utils import load_class_from_path


class LLMFactory:
    """
    Manages creation, caching, and retrieval of LLM clients for multiple LLM providers.
    """

    def __init__(self) -> None:
        self._clients: dict[LLMProvider, LLMClient] = {}
        self._project_clients: dict[tuple[str, LLMProvider], LLMClient] = {}

    def init_clients(self, configs: list[LLMConfig]):
        """
        Initialize and cache global clients for the given LLM provider configurations.
        """
        for config in configs:
            self.get_client(config)

    def get_client(
        self, config: LLMConfig, prompt_model: str | None = None, project_name: str | None = None
    ) -> LLMClient:
        """
        Retrieve a client instance for the specified provider and (optionally) project.

        The provider is resolved from `prompt_model` when possible (via model-name prefix),
        falling back to `config.provider`.

        If a project name is provided, this method checks for an existing client instance specific
        to that project. If none exists, it attempts to retrieve a project-specific API key.
        If the API key exists, it creates a new client, caches it and returns it.

        If no project name is given, this method checks for a global (default) client for the provider.
        If not already created, it retrieves the API key for the provider, creates the client, caches it and returns it.
        """
        provider = self._resolve_provider(config, prompt_model)

        # If a project name is provided, handle project-specific client retrieval/creation
        if project_name is not None:
            # Check if a project-specific client already exists
            key = (project_name, provider)
            if key in self._project_clients:
                return self._project_clients[key]
            # Attempt to retrieve a project-specific API key
            api_key = self._get_project_api_key(project_name, provider)
            if api_key is not None:
                # Create, cache, and return the new project-specific client
                self._project_clients[key] = self._create_client(provider, config, api_key)
                return self._project_clients[key]

        # If no global client for provider is found, retrieves the API key and creates the client
        if provider not in self._clients:
            api_key = self._get_api_key(provider)
            self._clients[provider] = self._create_client(provider, config, api_key)

        return self._clients[provider]

    async def close_clients(self):
        """
        Close all cached clients.
        """
        all_clients = list(self._clients.values()) + list(self._project_clients.values())
        for client in all_clients:
            await client.close()

    def _is_openai_model(self, model_name: str) -> bool:
        """
        Return True for OpenAI model names: gpt-* prefix or o-series (o1, o3, o4-mini, …).
        """
        return model_name.startswith("gpt-") or bool(re.match(r"^o\d+", model_name))

    def _resolve_provider(self, config: LLMConfig, prompt_model: str | None) -> LLMProvider:
        """
        Determine the LLM provider from the model name, falling back to `config.provider`.

        When the model is an OpenAI model (gpt-* or o-series), the configured provider is
        preserved if it is OPENAI or AZURE_OPENAI, so Azure deployments are routed correctly.
        For Claude models the provider is always ANTHROPIC regardless of config.
        """
        if prompt_model is not None:
            if self._is_openai_model(prompt_model):
                if config.provider in (LLMProvider.AZURE_OPENAI):
                    return config.provider
                return LLMProvider.OPENAI
            if prompt_model.startswith("claude-"):
                return LLMProvider.ANTHROPIC
        return config.provider

    def _get_api_key(self, provider: LLMProvider) -> str | None:
        """
        Load the API key from environment variables using the pattern '{PROVIDER}_API_KEY'.
        """
        if provider == LLMProvider.CUSTOM:
            return None  # Do not force 'CUSTOM_API_KEY' as environment variable
        env_key = f"{provider.value.upper()}_API_KEY"
        api_key = os.getenv(env_key)
        if not api_key:
            raise ValueError(
                f"API key for provider '{provider.value}' not found in environment variables."
            )
        return api_key

    def _normalize_project_name(self, project_name: str) -> str:
        """
        Replace all non-alphanumeric characters with underscores, then uppercase
        """
        return re.sub(r"\W+", "_", project_name).upper()

    def _get_project_api_key(self, project_name: str, provider: LLMProvider) -> str | None:
        """
        Load the project API key from environment variables using the pattern '{NORMALIZED_PROJECT_NAME}_{PROVIDER}_API_KEY'.
        """
        normalized = self._normalize_project_name(project_name)
        env_key = f"{normalized}_{provider.value.upper()}_API_KEY"
        return os.getenv(env_key)

    def _create_client(
        self, provider: LLMProvider, config: LLMConfig, api_key: str | None
    ) -> LLMClient:
        """
        Create an LLM client instance using the given LLMConfig and API key.
        """
        common_kwargs = self._get_common_client_kwargs(config)

        if provider == LLMProvider.OPENAI:
            return OpenAIClient(api_key=api_key, **common_kwargs)

        if config.provider == LLMProvider.AZURE_OPENAI:
            assert config.azure_endpoint is not None
            assert config.api_version is not None
            return AzureOpenAIClient(
                api_key=api_key,
                azure_endpoint=config.azure_endpoint,
                api_version=config.api_version,
                deployment_mapping=self._get_deployment_mapping(config),
                **common_kwargs,
            )

        if provider == LLMProvider.ANTHROPIC:
            return AnthropicClient(api_key=api_key, **common_kwargs)

        if provider == LLMProvider.CUSTOM:
            assert config.class_path is not None
            client_class: type[LLMClient] = load_class_from_path(config.class_path)
            return client_class(api_key, **common_kwargs)

        raise NotImplementedError(f"Unsupported LLM provider: '{provider}'.")

    def _get_common_client_kwargs(self, config: LLMConfig) -> dict[str, Any]:
        extra = config.model_extra or {}
        allowed_keys = {"timeout", "max_retries", "_strict_response_validation"}
        return {key: value for key, value in extra.items() if key in allowed_keys}

    def _get_deployment_mapping(self, config: LLMConfig) -> dict[str, str] | None:
        extra = config.model_extra or {}
        deployment_mapping = extra.get("deployment_mapping")

        if deployment_mapping is None:
            return None

        if not isinstance(deployment_mapping, dict):
            raise ValueError(
                "'deployment_mapping' must be a dictionary mapping deployment names to canonical model names."
            )

        if not all(
            isinstance(deployment_name, str) and isinstance(canonical_model, str)
            for deployment_name, canonical_model in deployment_mapping.items()
        ):
            raise ValueError(
                "'deployment_mapping' must only contain string keys and string values."
            )

        return deployment_mapping
