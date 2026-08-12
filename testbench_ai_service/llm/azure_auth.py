from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from testbench_ai_service.utils.naming import normalize_project_name

if TYPE_CHECKING:
    from azure.core.credentials_async import AsyncTokenCredential
    from openai.lib.azure import AsyncAzureADTokenProvider

AZURE_TOKEN_SCOPE = "https://cognitiveservices.azure.com/.default"

_ENV_SUFFIXES = ("AZURE_TENANT_ID", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET")


@dataclass(frozen=True)
class EntraIdCredentials:
    """Client credentials of an Entra ID service principal (app registration)."""

    tenant_id: str
    client_id: str
    # repr=False keeps the secret out of the default string form, so it cannot
    # reach a log line, an exception message or a pytest --showlocals dump.
    # It still takes part in __eq__ and __hash__.
    client_secret: str = field(repr=False)


def _env_names(project_name: str | None) -> tuple[str, str, str]:
    prefix = f"{normalize_project_name(project_name)}_" if project_name else ""
    return (
        f"{prefix}{_ENV_SUFFIXES[0]}",
        f"{prefix}{_ENV_SUFFIXES[1]}",
        f"{prefix}{_ENV_SUFFIXES[2]}",
    )


def resolve_entra_credentials(project_name: str | None = None) -> EntraIdCredentials | None:
    """
    Read Entra ID service principal credentials from the environment.

    Global credentials are read from 'AZURE_TENANT_ID', 'AZURE_CLIENT_ID' and
    'AZURE_CLIENT_SECRET'. Project credentials use the same names prefixed with
    the normalized project name.

    Args:
        project_name: TestBench project name, or None for the global credentials.

    Returns:
        The credentials, or None if a project has no credentials of its own and
        should therefore use the global service principal.

    Raises:
        ValueError: If the credentials are only partially configured, or if the
            global credentials are missing entirely.
    """
    tenant_name, client_name, secret_name = _env_names(project_name)
    tenant_id = os.getenv(tenant_name)
    client_id = os.getenv(client_name)
    client_secret = os.getenv(secret_name)

    names = (tenant_name, client_name, secret_name)
    values = (tenant_id, client_id, client_secret)

    if tenant_id and client_id and client_secret:
        return EntraIdCredentials(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret,
        )

    missing = [name for name, value in zip(names, values, strict=True) if not value]

    # A project without any credentials of its own falls back to the global ones.
    if project_name is not None and len(missing) == len(names):
        return None

    scope = f"project '{project_name}'" if project_name else "the global configuration"
    raise ValueError(
        f"Entra ID authentication for {scope} is incompletely configured. "
        f"Missing environment variable(s): {', '.join(missing)}."
    )


def create_token_provider(
    credentials: EntraIdCredentials,
) -> tuple[AsyncTokenCredential, AsyncAzureADTokenProvider]:
    """
    Create an async Azure credential and a matching bearer token provider.

    The credential holds an HTTP session and must be closed by the caller.

    Args:
        credentials: Entra ID service principal credentials.

    Returns:
        A tuple of the credential and the async token provider callable that
        'AsyncAzureOpenAI' accepts as 'azure_ad_token_provider'.

    Raises:
        ValueError: If 'azure-identity' or its async HTTP transport dependency
            ('aiohttp') is not installed.
    """
    try:
        # Imported lazily so azure-identity's import cost stays off the startup
        # path for API-key installations; a missing package becomes this
        # actionable ValueError instead of a crash at service start.
        #
        # The credential construction is inside the same 'try' on purpose:
        # ClientSecretCredential builds its async HTTP pipeline in __init__ and
        # imports AioHttpTransport there, so a missing 'aiohttp' surfaces as an
        # ImportError from this call rather than from the import statement.
        from azure.identity.aio import (  # noqa: PLC0415
            ClientSecretCredential,
            get_bearer_token_provider,
        )

        credential = ClientSecretCredential(
            tenant_id=credentials.tenant_id,
            client_id=credentials.client_id,
            client_secret=credentials.client_secret,
        )
        token_provider = get_bearer_token_provider(credential, AZURE_TOKEN_SCOPE)
    except ImportError as e:
        raise ValueError(
            "The 'azure-identity' package and its async HTTP transport are required for "
            "auth_method = 'entra_id'. Install them with "
            f"'pip install azure-identity aiohttp'. Import error: {e}"
        ) from e

    return credential, token_provider
