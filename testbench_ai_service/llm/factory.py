import os
import re

from dotenv import load_dotenv

from testbench_ai_service.config import LLMConfig
from testbench_ai_service.llm.base import LLMClient, LLMProvider
from testbench_ai_service.llm.openai import OpenAIClient
from testbench_ai_service.utils.import_utils import load_class_from_path

# Load environment variables from .env file
load_dotenv()


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

    def get_client(self, config: LLMConfig, project_name: str | None = None) -> LLMClient:
        """
        Retrieve a client instance for the specified provider and (optionally) project.

        If a project name is provided, this method checks for an existing client instance specific
        to that project. If none exists, it attempts to retrieve a project-specific API key.
        If the API key exists, it creates a new client, caches it and returns it.

        If no project name is given, this method checks for a global (default) client for the provider.
        If not already created, it retrieves the API key for the provider, creates the client, caches it and returns it.
        """
        # If a project name is provided, handle project-specific client retrieval/creation
        if project_name is not None:
            # Check if a project-specific client already exists
            key = (project_name, config.provider)
            if key in self._project_clients:
                return self._project_clients[key]
            # Attempt to retrieve a project-specific API key
            api_key = self._get_project_api_key(project_name, config.provider)
            if api_key is not None:
                # Create, cache, and return the new project-specific client
                self._project_clients[key] = self._create_client(config, api_key)
                return self._project_clients[key]

        # If no global client for provider is found, retrieves the API key and creates the client
        if config.provider not in self._clients:
            api_key = self._get_api_key(config.provider)
            self._clients[config.provider] = self._create_client(config, api_key)

        return self._clients[config.provider]

    async def close_clients(self):
        """
        Close all cached clients.
        """
        all_clients = list(self._clients.values()) + list(self._project_clients.values())
        for client in all_clients:
            await client.close()

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

    def _create_client(self, config: LLMConfig, api_key: str | None) -> LLMClient:
        """
        Create an LLM client instance using the given LLMConfig and API key.
        """
        if config.provider == LLMProvider.OPENAI:
            return OpenAIClient(api_key=api_key)

        if config.provider == LLMProvider.CUSTOM:
            assert config.class_path is not None
            client_class: type[LLMClient] = load_class_from_path(config.class_path)
            return client_class(api_key)

        raise NotImplementedError(f"Unsupported LLM provider: '{config.provider}'.")
