"""Where API keys and Entra ID credentials of the LLM providers come from.

Shared by the ``LLMFactory`` and the embedding clients of the test planner.
"""

import os

from testbench_ai_service.llm.azure_auth import EntraIdCredentials, resolve_entra_credentials
from testbench_ai_service.llm.base import AzureAuthMethod, LLMProvider
from testbench_ai_service.models.config import LLMConfig
from testbench_ai_service.utils.naming import normalize_project_name


def get_api_key(provider: LLMProvider) -> str | None:
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


def get_project_api_key(project_name: str, provider: LLMProvider) -> str | None:
    """
    Load the project API key from environment variables using the pattern
    '{NORMALIZED_PROJECT_NAME}_{PROVIDER}_API_KEY'.
    """
    normalized = normalize_project_name(project_name)
    return os.getenv(f"{normalized}_{provider.value.upper()}_API_KEY")


def uses_entra_id(provider: LLMProvider, config: LLMConfig) -> bool:
    """
    Return True when this provider/config combination authenticates via Entra ID.
    """
    return provider == LLMProvider.AZURE_OPENAI and config.auth_method == AzureAuthMethod.ENTRA_ID


def resolve_credential(
    provider: LLMProvider, config: LLMConfig, project_name: str | None = None
) -> str | EntraIdCredentials | None:
    """
    The project-specific credential if one is set, otherwise the global one.
    """
    entra_id = uses_entra_id(provider, config)
    if project_name is not None:
        credential = (
            resolve_entra_credentials(project_name)
            if entra_id
            else get_project_api_key(project_name, provider)
        )
        if credential is not None:
            return credential
    if entra_id:
        return resolve_entra_credentials(None)
    return get_api_key(provider)
