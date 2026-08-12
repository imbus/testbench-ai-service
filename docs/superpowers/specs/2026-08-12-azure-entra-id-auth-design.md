# Azure OpenAI Authentication via Microsoft Entra ID

**Date:** 2026-08-12
**Status:** Approved

## Problem

The AI service authenticates against Azure OpenAI with an API key only. The
customer's Security Operations team (AI Factory) approves API key
authentication solely for direct integration scenarios where it is explicitly
required. For application development, Entra ID is the mandated method. The
current implementation therefore blocks these customers.

The deployment is on-premise, so managed identity is not available.
Authentication uses an Entra ID service principal (app registration) with a
client secret.

## Goal

An operator can configure the Azure OpenAI connection to authenticate via an
Entra ID service principal instead of an API key, globally and per TestBench
project, without changing behaviour for existing API-key installations.

## Out of scope

- Entra ID or any token-based authentication for other LLM providers.
- A cross-provider authentication framework.
- Managed identity (not applicable on-premise).
- Certificate-based service principal credentials.
- Registering the app and assigning roles in the customer's Azure tenant.
  This is the customer's responsibility and is documented only.

## Design

### 1. Configuration surface

A new enum in `testbench_ai_service/llm/base.py`, alongside `LLMProvider`:

```python
class AzureAuthMethod(str, Enum):
    API_KEY = "api_key"
    ENTRA_ID = "entra_id"

    def __str__(self):
        return self.value
```

`LLMConfig` in `testbench_ai_service/models/config.py` gains a typed field:

```python
auth_method: AzureAuthMethod = AzureAuthMethod.API_KEY
```

`LLMConfig.validate_config` rejects `auth_method = "entra_id"` for any provider
other than `azure_openai`, using the existing `raise_field_validation_error`
helper. A flag placed on the wrong provider then fails at startup instead of
being silently ignored.

The default remains `api_key`, so existing configurations are unaffected.

Example configuration:

```toml
[testbench-ai-service.llm_config]
provider = "azure_openai"
auth_method = "entra_id"          # or "api_key" (default)
azure_endpoint = "https://your-resource.openai.azure.com"
api_version = "2025-04-01-preview"
```

### 2. Credential resolution — new module `testbench_ai_service/llm/azure_auth.py`

This module has one responsibility: turn environment variables into an Azure
token provider. It knows nothing about the factory or the client.

**`EntraIdCredentials`** — value object holding `tenant_id`, `client_id` and
`client_secret`.

**`resolve_entra_credentials(project_name: str | None) -> EntraIdCredentials | None`**

Reads three environment variables:

| Scope | Variables |
| --- | --- |
| Global | `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET` |
| Project | `{NORMALIZED_PROJECT}_AZURE_TENANT_ID`, `{NORMALIZED_PROJECT}_AZURE_CLIENT_ID`, `{NORMALIZED_PROJECT}_AZURE_CLIENT_SECRET` |

The project prefix follows the existing convention: the project name uppercased
with every non-alphanumeric character replaced by an underscore. That logic
currently lives in `LLMFactory._normalize_project_name`. To avoid duplicating
it, the function moves to `testbench_ai_service/utils/naming.py` as
`normalize_project_name`, and `LLMFactory._normalize_project_name` becomes a
one-line delegation so existing callers and tests are unaffected.

Resolution rules:

- **Project scope, none of the three set** → return `None`. The caller falls
  back to the global service principal. This mirrors the existing
  project-API-key fallback.
- **Project scope, some but not all set** → raise `ValueError` naming the
  missing variables. A half-configured project principal must not silently fall
  back to the global one; that would authenticate as an unintended identity.
- **Global scope, any missing** → raise `ValueError` naming the missing
  variables.

**`create_token_provider(credentials) -> tuple[AsyncTokenCredential, AsyncAzureADTokenProvider]`**

Builds an `azure.identity.aio.ClientSecretCredential` and wraps it with
`azure.identity.aio.get_bearer_token_provider` for the scope
`https://cognitiveservices.azure.com/.default`. It returns both the credential
and the provider, because the credential owns an HTTP session that must be
closed on shutdown.

`azure.identity` is imported lazily inside this function. A missing package
then produces a clear, actionable error at client creation rather than an
import failure at service startup.

The asynchronous variants are required: `AsyncAzureOpenAI` declares
`azure_ad_token_provider: AsyncAzureADTokenProvider | None`, which is an async
callable. The synchronous `azure.identity` equivalents do not satisfy it.

### 3. Client wiring — `testbench_ai_service/llm/openai.py`

`AzureOpenAIClient.__init__` accepts either an `api_key` or an
`azure_ad_token_provider` together with the owning `credential`, and passes
whichever is set to `AsyncAzureOpenAI`.

`AzureOpenAIClient.close()` is overridden to close the credential in addition
to the client. Without this the credential's HTTP session leaks on shutdown.

`query_llm` and the deployment mapping logic are unchanged; authentication is
orthogonal to request routing.

### 4. Factory wiring — `testbench_ai_service/llm/factory.py`

The caching and provider-resolution logic in `get_client` is unchanged. Only
the credential lookup becomes polymorphic:

```python
def _uses_entra_id(self, provider, config) -> bool:
    return (
        provider == LLMProvider.AZURE_OPENAI
        and config.auth_method == AzureAuthMethod.ENTRA_ID
    )

def _get_credential(self, provider, config) -> str | EntraIdCredentials | None:
    if self._uses_entra_id(provider, config):
        return resolve_entra_credentials(None)
    return self._get_api_key(provider)

def _get_project_credential(self, project_name, provider, config) -> str | EntraIdCredentials | None:
    if self._uses_entra_id(provider, config):
        return resolve_entra_credentials(project_name)
    return self._get_project_api_key(project_name, provider)
```

`_create_client` branches on the credential type and constructs the
`AzureOpenAIClient` with either an API key or a token provider.

`_get_api_key` and `_get_project_api_key` keep their current names and
behaviour, so existing tests that patch them continue to apply. Critically, in
Entra ID mode `_get_api_key` is never called, so its
`API key for provider 'azure_openai' not found` raise cannot trigger.

Client caching is unaffected: a project with its own service principal gets its
own cached client under the existing `(project_name, provider)` key, exactly as
a project with its own API key does today.

### 5. Dependency and packaging

`azure-identity>=1.25.0,<2.0.0` is added to `dependencies` in `pyproject.toml`
as a hard dependency rather than an optional extra. The shipped artifact is a
PyInstaller binary; an operator cannot install an extra into a frozen build, so
an optional dependency would be unusable in practice. It transitively brings in
`azure-core` and `msal`.

`testbench-ai-service.spec` adds `collect_submodules("azure.identity")` and
`collect_submodules("msal")` to `hiddenimports`. azure-identity resolves
credential classes dynamically, which PyInstaller's static analysis does not
follow. Without these entries the binary builds successfully and fails only at
runtime on an Entra-configured installation.

### 6. Error handling and logging

| Situation | Behaviour |
| --- | --- |
| Global env vars missing | `ValueError` at client creation naming each unset variable |
| Project env vars partially set | `ValueError` naming the missing variables; no fallback to the global principal |
| `azure-identity` not importable | `ValueError` stating the package is required for `auth_method = "entra_id"` |
| `auth_method = "entra_id"` on a non-Azure provider | Pydantic validation error at startup |
| Invalid secret, expired secret, or missing role assignment | Azure's `ClientAuthenticationError` surfaces on the first request and is logged at `error` with tenant ID and client ID |

The client secret is never logged and never included in an exception message.

At client creation the service logs at `info` which authentication method is in
use and for which endpoint. This makes the active method visible in the log,
which is what allows an operator to evidence compliance.

### 7. Testing

All tests are unit tests with mocked dependencies. No test contacts Azure, and
nothing is added to the `prompt_engineering` marker.

**Configuration** (`tests/unit/test_config.py`)

- `auth_method = "entra_id"` is accepted for `provider = "azure_openai"`.
- `auth_method = "entra_id"` is rejected for `openai`, `anthropic` and `custom`.
- Omitting `auth_method` yields `api_key`.

**Credential resolution** (`tests/unit/llm/test_azure_auth.py`, new)

- All three global variables set → credentials returned.
- All three project variables set → project credentials returned.
- No project variables set → `None` returned.
- Each partial permutation, global and project → raises, and the message names
  the missing variables.
- The token provider is created with the
  `https://cognitiveservices.azure.com/.default` scope.
- A missing `azure.identity` import raises the documented error.

**Factory** (`tests/unit/llm/test_factory.py`)

- In Entra ID mode `_get_api_key` is never called, even with
  `AZURE_OPENAI_API_KEY` unset. This is the regression guard for the raise in
  `_get_api_key`.
- A project service principal takes precedence over the global one.
- A project without its own principal reuses the global client.
- API key mode behaviour is unchanged.

**Client** (`tests/unit/llm/test_openai.py`)

- `AsyncAzureOpenAI` receives `azure_ad_token_provider` and no `api_key` in
  Entra ID mode.
- `AsyncAzureOpenAI` receives `api_key` and no token provider in API key mode.
- `close()` closes both the client and the credential.

### 8. Documentation

`docs/llm-providers/azure-openai-setup.md` gains an **Authentication methods**
section covering both paths, including:

- The customer-side app registration steps, explicitly marked as the customer's
  responsibility: register the application, create a client secret, and assign
  the **Cognitive Services OpenAI User** role on the Azure OpenAI resource. The
  missing role assignment is the most common cause of a correct-looking
  configuration still returning 401 and is called out prominently.
- Environment variable tables for global and project scope.
- A note that the client secret expires and must be rotated.
- New troubleshooting rows for the failure modes in section 6.

`config_example.toml` gains a commented `auth_method` line in the
`llm_config` section.

`CHANGELOG.md` gains an `Added` entry under a new `## [Unreleased]` heading
placed above `## [1.0.1]`.

## Files touched

| File | Change |
| --- | --- |
| `testbench_ai_service/llm/base.py` | Add `AzureAuthMethod` enum |
| `testbench_ai_service/llm/azure_auth.py` | New module |
| `testbench_ai_service/llm/openai.py` | Token provider support in `AzureOpenAIClient` |
| `testbench_ai_service/llm/factory.py` | Credential dispatch |
| `testbench_ai_service/models/config.py` | `auth_method` field and validation |
| `testbench_ai_service/utils/naming.py` | New; hosts `normalize_project_name` |
| `pyproject.toml` | `azure-identity` dependency |
| `testbench-ai-service.spec` | PyInstaller hidden imports |
| `config_example.toml` | Commented `auth_method` |
| `docs/llm-providers/azure-openai-setup.md` | Authentication methods section |
| `CHANGELOG.md` | Added entry |
| `tests/unit/test_config.py` | Validation tests |
| `tests/unit/llm/test_azure_auth.py` | New test module |
| `tests/unit/llm/test_factory.py` | Dispatch tests |
| `tests/unit/llm/test_openai.py` | Client wiring tests |

## Acceptance criteria

1. With `auth_method = "entra_id"` and the three global environment variables
   set, the service authenticates against Azure OpenAI without
   `AZURE_OPENAI_API_KEY` being set.
2. A project with its own service principal environment variables uses that
   principal; a project without them uses the global one.
3. Missing or partial credentials produce an error naming the exact variables.
4. The client secret appears in no log entry and no error message.
5. Existing API key configurations behave exactly as before.
6. The PyInstaller binary works with an Entra ID configuration.
