# Azure OpenAI Entra ID Authentication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an operator authenticate the Azure OpenAI connection with a Microsoft Entra ID service principal instead of an API key, configured globally or per TestBench project.

**Architecture:** A new `auth_method` field on `LLMConfig` selects the method. A new self-contained module `llm/azure_auth.py` turns environment variables into an async Azure token provider. `LLMFactory` dispatches on that flag when looking up credentials, leaving its caching logic untouched, and `AzureOpenAIClient` accepts either an API key or a token provider.

**Tech Stack:** Python 3.10+, Pydantic v2, `openai` (`AsyncAzureOpenAI`), `azure-identity` (async credentials), pytest with `pytest-asyncio` in auto mode.

**Spec:** `docs/superpowers/specs/2026-08-12-azure-entra-id-auth-design.md`

## Global Constraints

- Default behaviour must not change: `auth_method` defaults to `api_key`, and existing API-key installations keep working exactly as before.
- The client secret is never logged and never included in an exception message.
- New dependency floor: `azure-identity>=1.25.0,<2.0.0`.
- Azure token scope, used verbatim: `https://cognitiveservices.azure.com/.default`.
- Environment variable names, used verbatim: `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`; project-scoped variants are prefixed `{NORMALIZED_PROJECT}_`.
- `AsyncAzureOpenAI.azure_ad_token_provider` requires an **async** provider, so `azure.identity.aio` must be used, not the synchronous `azure.identity`.
- All tests are unit tests with mocked dependencies. No test contacts Azure. Nothing is added to the `prompt_engineering` pytest marker.
- Lint and type rules are enforced by the repo: `ruff` (line length 100, `B` rules active — `zip()` needs an explicit `strict=` argument) and `mypy` in strict-optional mode over `testbench_ai_service` and `tests`.
- Run the full check before each commit: `.venv/Scripts/python.exe -m pytest -q` and `.venv/Scripts/python.exe -m mypy`.

---

### Task 1: Configuration surface — `auth_method`

**Files:**
- Modify: `testbench_ai_service/llm/base.py` (add enum after `LLMProvider`, around line 15)
- Modify: `testbench_ai_service/models/config.py:10-40`
- Test: `tests/unit/test_config.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `AzureAuthMethod` enum with members `API_KEY = "api_key"` and `ENTRA_ID = "entra_id"`, importable from `testbench_ai_service.llm.base`. `LLMConfig.auth_method: AzureAuthMethod` defaulting to `AzureAuthMethod.API_KEY`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/test_config.py`. First extend the existing import of `testbench_ai_service.llm.base` in that file to also import `AzureAuthMethod`, then add these methods to the existing `TestLLMConfig` class:

```python
    def test_auth_method_defaults_to_api_key(self):
        cfg = LLMConfig()
        assert cfg.auth_method == AzureAuthMethod.API_KEY

    def test_azure_openai_provider_accepts_entra_id_auth(self):
        cfg = LLMConfig(
            provider=LLMProvider.AZURE_OPENAI,
            auth_method=AzureAuthMethod.ENTRA_ID,
            azure_endpoint="https://example.openai.azure.com",
            api_version="2024-10-21",
        )
        assert cfg.auth_method == AzureAuthMethod.ENTRA_ID

    @pytest.mark.parametrize(
        "provider",
        [LLMProvider.OPENAI, LLMProvider.ANTHROPIC],
    )
    def test_entra_id_auth_rejected_for_non_azure_provider(self, provider):
        with pytest.raises(ValidationError):
            LLMConfig(provider=provider, auth_method=AzureAuthMethod.ENTRA_ID)

    def test_auth_method_accepts_plain_string_from_toml(self):
        cfg = LLMConfig(
            provider=LLMProvider.AZURE_OPENAI,
            auth_method="entra_id",
            azure_endpoint="https://example.openai.azure.com",
            api_version="2024-10-21",
        )
        assert cfg.auth_method == AzureAuthMethod.ENTRA_ID
```

The last test matters because `config.toml` supplies a bare string, never an enum member.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_config.py -k auth_method -v`
Expected: FAIL with `ImportError: cannot import name 'AzureAuthMethod'`

- [ ] **Step 3: Add the enum**

In `testbench_ai_service/llm/base.py`, directly below the `LLMProvider` class:

```python
class AzureAuthMethod(str, Enum):
    API_KEY = "api_key"
    ENTRA_ID = "entra_id"

    def __str__(self):
        return self.value
```

- [ ] **Step 4: Add the field and validation**

In `testbench_ai_service/models/config.py`, change the import on line 5 to:

```python
from testbench_ai_service.llm.base import AzureAuthMethod, LLMProvider
```

Add the field to `LLMConfig` immediately after `provider`:

```python
    auth_method: AzureAuthMethod = AzureAuthMethod.API_KEY
```

Insert this block at the **start** of `validate_config`, before the `CUSTOM` check:

```python
        if (
            self.auth_method == AzureAuthMethod.ENTRA_ID
            and self.provider != LLMProvider.AZURE_OPENAI
        ):
            raise_field_validation_error(
                self,
                "auth_method",
                ValueError(
                    "'auth_method = entra_id' is only supported for provider 'azure_openai'."
                ),
            )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_config.py -v`
Expected: PASS, including all pre-existing tests in the file.

- [ ] **Step 6: Commit**

```bash
git add testbench_ai_service/llm/base.py testbench_ai_service/models/config.py tests/unit/test_config.py
git commit -m "feat: Add auth_method config field for Azure OpenAI"
```

---

### Task 2: Extract `normalize_project_name` to a shared utility

Both `LLMFactory` and the new `azure_auth` module need to build environment variable names from a project name. Duplicating the rule would let the API-key and Entra ID variable names drift apart.

**Files:**
- Create: `testbench_ai_service/utils/naming.py`
- Modify: `testbench_ai_service/llm/factory.py:111-115`
- Test: `tests/unit/utils/test_naming.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `normalize_project_name(project_name: str) -> str` in `testbench_ai_service.utils.naming`. `LLMFactory._normalize_project_name` keeps its name and signature, delegating to the new function.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/utils/test_naming.py`:

```python
import pytest

from testbench_ai_service.utils.naming import normalize_project_name


@pytest.mark.parametrize(
    ("project_name", "expected"),
    [
        ("Car Configurator", "CAR_CONFIGURATOR"),
        ("my-project", "MY_PROJECT"),
        ("Projekt (2026)", "PROJEKT_2026_"),
        ("already_normalized", "ALREADY_NORMALIZED"),
    ],
)
def test_normalize_project_name(project_name, expected):
    assert normalize_project_name(project_name) == expected


def test_matches_factory_helper():
    """The factory helper must stay in lockstep with the shared function."""
    from testbench_ai_service.llm.factory import LLMFactory

    factory = LLMFactory()
    assert factory._normalize_project_name("Car Configurator") == normalize_project_name(
        "Car Configurator"
    )
```

`"Projekt (2026)"` normalises to `PROJEKT_2026_` with a trailing underscore because `\W+` also matches the closing parenthesis. That is the existing behaviour and this test pins it so the extraction is provably behaviour-preserving.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/utils/test_naming.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'testbench_ai_service.utils.naming'`

- [ ] **Step 3: Create the module**

`testbench_ai_service/utils/naming.py`:

```python
import re


def normalize_project_name(project_name: str) -> str:
    """
    Normalize a TestBench project name for use in environment variable names.

    Replaces every run of non-alphanumeric characters with a single underscore
    and uppercases the result, e.g. "Car Configurator" -> "CAR_CONFIGURATOR".
    """
    return re.sub(r"\W+", "_", project_name).upper()
```

- [ ] **Step 4: Delegate from the factory**

In `testbench_ai_service/llm/factory.py`, add to the imports:

```python
from testbench_ai_service.utils.naming import normalize_project_name
```

Replace the body of `_normalize_project_name` (lines 111-115) with:

```python
    def _normalize_project_name(self, project_name: str) -> str:
        """
        Replace all non-alphanumeric characters with underscores, then uppercase
        """
        return normalize_project_name(project_name)
```

Check whether `import re` at the top of `factory.py` is still used — it is, by `_is_openai_model` and `_get_project_api_key`. Leave it.

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/utils/test_naming.py tests/unit/llm/test_factory.py -v`
Expected: PASS, including all pre-existing factory tests.

- [ ] **Step 6: Commit**

```bash
git add testbench_ai_service/utils/naming.py testbench_ai_service/llm/factory.py tests/unit/utils/test_naming.py
git commit -m "refactor: Extract normalize_project_name to shared utility"
```

---

### Task 3: Credential resolution from the environment

**Files:**
- Create: `testbench_ai_service/llm/azure_auth.py`
- Test: `tests/unit/llm/test_azure_auth.py`

**Interfaces:**
- Consumes: `normalize_project_name` from Task 2.
- Produces:
  - `AZURE_TOKEN_SCOPE: str` constant.
  - `EntraIdCredentials` frozen dataclass with fields `tenant_id`, `client_id`, `client_secret` (all `str`).
  - `resolve_entra_credentials(project_name: str | None = None) -> EntraIdCredentials | None`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/llm/test_azure_auth.py`:

```python
import pytest

from testbench_ai_service.llm.azure_auth import (
    EntraIdCredentials,
    resolve_entra_credentials,
)

GLOBAL_VARS = ("AZURE_TENANT_ID", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET")
PROJECT_VARS = (
    "CAR_CONFIGURATOR_AZURE_TENANT_ID",
    "CAR_CONFIGURATOR_AZURE_CLIENT_ID",
    "CAR_CONFIGURATOR_AZURE_CLIENT_SECRET",
)


@pytest.fixture(autouse=True)
def _clear_azure_env(monkeypatch):
    """Ensure a developer's own Azure environment cannot influence these tests."""
    for name in GLOBAL_VARS + PROJECT_VARS:
        monkeypatch.delenv(name, raising=False)


class TestResolveEntraCredentialsGlobal:
    def test_returns_credentials_when_all_variables_set(self, monkeypatch):
        monkeypatch.setenv("AZURE_TENANT_ID", "tenant-1")
        monkeypatch.setenv("AZURE_CLIENT_ID", "client-1")
        monkeypatch.setenv("AZURE_CLIENT_SECRET", "secret-1")

        result = resolve_entra_credentials()

        assert result == EntraIdCredentials(
            tenant_id="tenant-1", client_id="client-1", client_secret="secret-1"
        )

    def test_raises_when_nothing_is_set(self):
        with pytest.raises(ValueError) as exc_info:
            resolve_entra_credentials()
        message = str(exc_info.value)
        for name in GLOBAL_VARS:
            assert name in message

    @pytest.mark.parametrize("missing", GLOBAL_VARS)
    def test_raises_and_names_the_missing_variable(self, monkeypatch, missing):
        for name in GLOBAL_VARS:
            if name != missing:
                monkeypatch.setenv(name, "value")

        with pytest.raises(ValueError) as exc_info:
            resolve_entra_credentials()

        message = str(exc_info.value)
        assert missing in message
        for name in GLOBAL_VARS:
            if name != missing:
                assert name not in message.split("Missing environment variable(s):")[1]

    def test_empty_string_counts_as_unset(self, monkeypatch):
        monkeypatch.setenv("AZURE_TENANT_ID", "")
        monkeypatch.setenv("AZURE_CLIENT_ID", "client-1")
        monkeypatch.setenv("AZURE_CLIENT_SECRET", "secret-1")

        with pytest.raises(ValueError, match="AZURE_TENANT_ID"):
            resolve_entra_credentials()


class TestResolveEntraCredentialsProject:
    def test_returns_project_credentials(self, monkeypatch):
        monkeypatch.setenv("CAR_CONFIGURATOR_AZURE_TENANT_ID", "tenant-p")
        monkeypatch.setenv("CAR_CONFIGURATOR_AZURE_CLIENT_ID", "client-p")
        monkeypatch.setenv("CAR_CONFIGURATOR_AZURE_CLIENT_SECRET", "secret-p")

        result = resolve_entra_credentials("Car Configurator")

        assert result == EntraIdCredentials(
            tenant_id="tenant-p", client_id="client-p", client_secret="secret-p"
        )

    def test_returns_none_when_no_project_variables_set(self):
        assert resolve_entra_credentials("Car Configurator") is None

    def test_global_variables_do_not_satisfy_a_project_lookup(self, monkeypatch):
        for name in GLOBAL_VARS:
            monkeypatch.setenv(name, "value")

        assert resolve_entra_credentials("Car Configurator") is None

    @pytest.mark.parametrize("present", PROJECT_VARS)
    def test_partial_project_configuration_raises(self, monkeypatch, present):
        monkeypatch.setenv(present, "value")

        with pytest.raises(ValueError) as exc_info:
            resolve_entra_credentials("Car Configurator")

        message = str(exc_info.value)
        assert "Car Configurator" in message
        for name in PROJECT_VARS:
            if name != present:
                assert name in message

    def test_secret_value_is_not_in_the_error_message(self, monkeypatch):
        monkeypatch.setenv("CAR_CONFIGURATOR_AZURE_CLIENT_SECRET", "super-secret-value")

        with pytest.raises(ValueError) as exc_info:
            resolve_entra_credentials("Car Configurator")

        assert "super-secret-value" not in str(exc_info.value)
```

`test_global_variables_do_not_satisfy_a_project_lookup` is the one that pins the fallback contract: a project lookup returns `None` so the caller falls back to the global client, rather than reading global variables under a project name.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/llm/test_azure_auth.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'testbench_ai_service.llm.azure_auth'`

- [ ] **Step 3: Create the module**

`testbench_ai_service/llm/azure_auth.py`:

```python
from __future__ import annotations

import os
from dataclasses import dataclass

from testbench_ai_service.utils.naming import normalize_project_name

AZURE_TOKEN_SCOPE = "https://cognitiveservices.azure.com/.default"

_ENV_SUFFIXES = ("AZURE_TENANT_ID", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET")


@dataclass(frozen=True)
class EntraIdCredentials:
    """Client credentials of an Entra ID service principal (app registration)."""

    tenant_id: str
    client_id: str
    client_secret: str


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
```

Note the `strict=True` on `zip` — ruff's `B905` rule is active and rejects it otherwise.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/llm/test_azure_auth.py -v`
Expected: PASS (14 tests)

- [ ] **Step 5: Commit**

```bash
git add testbench_ai_service/llm/azure_auth.py tests/unit/llm/test_azure_auth.py
git commit -m "feat: Resolve Entra ID credentials from environment"
```

---

### Task 4: Token provider, dependency and packaging

**Files:**
- Modify: `pyproject.toml:45-62` (dependencies)
- Modify: `testbench_ai_service/llm/azure_auth.py` (add `create_token_provider`)
- Modify: `testbench-ai-service.spec:29-55` (hidden imports)
- Test: `tests/unit/llm/test_azure_auth.py`

**Interfaces:**
- Consumes: `EntraIdCredentials`, `AZURE_TOKEN_SCOPE` from Task 3.
- Produces: `create_token_provider(credentials: EntraIdCredentials) -> tuple[AsyncTokenCredential, AsyncAzureADTokenProvider]`. The first element is the credential object, which the caller owns and must close; the second is the async callable passed to `AsyncAzureOpenAI(azure_ad_token_provider=...)`.

- [ ] **Step 1: Add the dependency**

In `pyproject.toml`, add to the `dependencies` list, after the `anthropic` line:

```toml
  "azure-identity>=1.25.0,<2.0.0",
```

Install it:

```bash
.venv/Scripts/python.exe -m pip install "azure-identity>=1.25.0,<2.0.0"
```

- [ ] **Step 2: Write the failing tests**

Add to `tests/unit/llm/test_azure_auth.py`. Extend the imports at the top of the file:

```python
import builtins
import sys
from unittest.mock import MagicMock

from testbench_ai_service.llm.azure_auth import (
    AZURE_TOKEN_SCOPE,
    EntraIdCredentials,
    create_token_provider,
    resolve_entra_credentials,
)
```

Then append this class:

```python
class TestCreateTokenProvider:
    def _fake_identity_module(self):
        module = MagicMock()
        module.ClientSecretCredential.return_value = MagicMock(name="credential")
        module.get_bearer_token_provider.return_value = MagicMock(name="provider")
        return module

    def test_builds_credential_and_provider(self, monkeypatch):
        module = self._fake_identity_module()
        monkeypatch.setitem(sys.modules, "azure.identity.aio", module)

        credentials = EntraIdCredentials(
            tenant_id="tenant-1", client_id="client-1", client_secret="secret-1"
        )
        credential, provider = create_token_provider(credentials)

        assert credential is module.ClientSecretCredential.return_value
        assert provider is module.get_bearer_token_provider.return_value
        module.ClientSecretCredential.assert_called_once_with(
            tenant_id="tenant-1",
            client_id="client-1",
            client_secret="secret-1",
        )

    def test_uses_cognitive_services_scope(self, monkeypatch):
        module = self._fake_identity_module()
        monkeypatch.setitem(sys.modules, "azure.identity.aio", module)

        create_token_provider(
            EntraIdCredentials(tenant_id="t", client_id="c", client_secret="s")
        )

        module.get_bearer_token_provider.assert_called_once_with(
            module.ClientSecretCredential.return_value,
            "https://cognitiveservices.azure.com/.default",
        )

    def test_scope_constant_matches_azure_documentation(self):
        assert AZURE_TOKEN_SCOPE == "https://cognitiveservices.azure.com/.default"

    def test_missing_azure_identity_raises_actionable_error(self, monkeypatch):
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "azure.identity.aio":
                raise ImportError("No module named 'azure'")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)

        with pytest.raises(ValueError, match="azure-identity"):
            create_token_provider(
                EntraIdCredentials(tenant_id="t", client_id="c", client_secret="s")
            )

    def test_secret_is_not_in_the_import_error_message(self, monkeypatch):
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "azure.identity.aio":
                raise ImportError("No module named 'azure'")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)

        with pytest.raises(ValueError) as exc_info:
            create_token_provider(
                EntraIdCredentials(
                    tenant_id="t", client_id="c", client_secret="super-secret-value"
                )
            )

        assert "super-secret-value" not in str(exc_info.value)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/llm/test_azure_auth.py -k TokenProvider -v`
Expected: FAIL with `ImportError: cannot import name 'create_token_provider'`

- [ ] **Step 4: Implement `create_token_provider`**

In `testbench_ai_service/llm/azure_auth.py`, extend the header imports:

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from azure.core.credentials_async import AsyncTokenCredential
    from openai.lib.azure import AsyncAzureADTokenProvider
```

Append the function:

```python
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
        ValueError: If the 'azure-identity' package is not installed.
    """
    try:
        from azure.identity.aio import ClientSecretCredential, get_bearer_token_provider
    except ImportError as e:
        raise ValueError(
            "The 'azure-identity' package is required for auth_method = 'entra_id'. "
            "Install it with 'pip install azure-identity'."
        ) from e

    credential = ClientSecretCredential(
        tenant_id=credentials.tenant_id,
        client_id=credentials.client_id,
        client_secret=credentials.client_secret,
    )
    return credential, get_bearer_token_provider(credential, AZURE_TOKEN_SCOPE)
```

The import sits inside the function on purpose: it keeps `azure-identity`'s import cost off the startup path for API-key installations, and it turns a missing package into the actionable `ValueError` above instead of a crash at service start.

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/llm/test_azure_auth.py -v`
Expected: PASS (19 tests)

- [ ] **Step 6: Add the PyInstaller hidden imports**

In `testbench-ai-service.spec`, add these two entries to the `hiddenimports` tuple, next to the existing `collect_submodules` calls (around line 32):

```python
    + collect_submodules("azure.identity")
    + collect_submodules("msal")
```

azure-identity resolves credential classes dynamically, which PyInstaller's static analysis does not follow. Without these entries the binary builds successfully and fails only at runtime on an Entra-configured installation.

- [ ] **Step 7: Verify the type check passes**

Run: `.venv/Scripts/python.exe -m mypy`
Expected: no errors in `azure_auth.py`. If mypy reports missing stubs for `azure.*`, do **not** silence it globally — `azure-identity` ships a `py.typed` marker, so a stub error means the install in step 1 did not complete.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml testbench_ai_service/llm/azure_auth.py tests/unit/llm/test_azure_auth.py testbench-ai-service.spec
git commit -m "feat: Add Azure AD token provider for Entra ID auth"
```

---

### Task 5: Token provider support in `AzureOpenAIClient`

**Files:**
- Modify: `testbench_ai_service/llm/openai.py:202-221` (constructor) and add a `close` override
- Test: `tests/unit/llm/test_openai.py`

**Interfaces:**
- Consumes: nothing from earlier tasks at runtime; the types come from `openai` and `azure.core`.
- Produces: `AzureOpenAIClient.__init__(api_key, azure_endpoint, api_version, deployment_mapping=None, azure_ad_token_provider=None, credential=None, timeout=NOT_GIVEN, max_retries=DEFAULT_MAX_RETRIES, _strict_response_validation=False)` and an overridden `async def close(self)`. The `api_key` parameter stays first and positional so existing call sites are unaffected.

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/llm/test_openai.py`. The file already imports `AzureOpenAIClient`; add `MagicMock` and `patch` to the `unittest.mock` import if not already present. Append this class:

```python
class TestAzureOpenAIClientAuthentication:
    """Tests for how ``AzureOpenAIClient`` passes credentials to the SDK."""

    def test_api_key_mode_passes_key_and_no_token_provider(self):
        with patch("testbench_ai_service.llm.openai.AsyncAzureOpenAI") as mock_sdk:
            AzureOpenAIClient(
                api_key="test-key",
                azure_endpoint="https://example.openai.azure.com",
                api_version="2024-10-21",
            )

        kwargs = mock_sdk.call_args.kwargs
        assert kwargs["api_key"] == "test-key"
        assert kwargs["azure_ad_token_provider"] is None

    def test_entra_id_mode_passes_token_provider_and_no_api_key(self):
        token_provider = MagicMock(name="token_provider")

        with patch("testbench_ai_service.llm.openai.AsyncAzureOpenAI") as mock_sdk:
            AzureOpenAIClient(
                api_key=None,
                azure_endpoint="https://example.openai.azure.com",
                api_version="2024-10-21",
                azure_ad_token_provider=token_provider,
                credential=AsyncMock(),
            )

        kwargs = mock_sdk.call_args.kwargs
        assert kwargs["api_key"] is None
        assert kwargs["azure_ad_token_provider"] is token_provider

    async def test_close_closes_client_and_credential(self):
        credential = AsyncMock()

        with patch("testbench_ai_service.llm.openai.AsyncAzureOpenAI"):
            client = AzureOpenAIClient(
                api_key=None,
                azure_endpoint="https://example.openai.azure.com",
                api_version="2024-10-21",
                azure_ad_token_provider=MagicMock(),
                credential=credential,
            )
        client.client.close = AsyncMock()

        await client.close()

        client.client.close.assert_awaited_once()
        credential.close.assert_awaited_once()

    async def test_close_without_credential_closes_only_the_client(self):
        with patch("testbench_ai_service.llm.openai.AsyncAzureOpenAI"):
            client = AzureOpenAIClient(
                api_key="test-key",
                azure_endpoint="https://example.openai.azure.com",
                api_version="2024-10-21",
            )
        client.client.close = AsyncMock()

        await client.close()

        client.client.close.assert_awaited_once()

    def test_deployment_mapping_still_defaults_to_empty_dict(self):
        with patch("testbench_ai_service.llm.openai.AsyncAzureOpenAI"):
            client = AzureOpenAIClient(
                api_key="test-key",
                azure_endpoint="https://example.openai.azure.com",
                api_version="2024-10-21",
            )

        assert client.deployment_mapping == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/llm/test_openai.py -k Authentication -v`
Expected: FAIL with `TypeError: __init__() got an unexpected keyword argument 'azure_ad_token_provider'`

- [ ] **Step 3: Extend the constructor and override `close`**

In `testbench_ai_service/llm/openai.py`, extend the type imports at the top:

```python
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from azure.core.credentials_async import AsyncTokenCredential
    from openai.lib.azure import AsyncAzureADTokenProvider
```

Replace `AzureOpenAIClient.__init__` (lines 203-221) with:

```python
    def __init__(
        self,
        api_key: str | None,
        azure_endpoint: str,
        api_version: str,
        deployment_mapping: dict[str, str] | None = None,
        azure_ad_token_provider: AsyncAzureADTokenProvider | None = None,
        credential: AsyncTokenCredential | None = None,
        timeout: float | Timeout | NotGiven | None = NOT_GIVEN,
        max_retries: int = DEFAULT_MAX_RETRIES,
        _strict_response_validation: bool = False,
    ):
        self.client = AsyncAzureOpenAI(
            api_key=api_key,
            azure_ad_token_provider=azure_ad_token_provider,
            azure_endpoint=azure_endpoint,
            api_version=api_version,
            timeout=timeout,
            max_retries=max_retries,
            _strict_response_validation=_strict_response_validation,
        )
        self.credential = credential
        self.deployment_mapping = deployment_mapping or {}
```

Append this method to the end of the class, after `query_llm`:

```python
    async def close(self):
        await self.client.close()
        if self.credential is not None:
            await self.credential.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/llm/test_openai.py -v`
Expected: PASS, including the pre-existing `TestAzureOpenAIClientQueryLlm` tests.

- [ ] **Step 5: Commit**

```bash
git add testbench_ai_service/llm/openai.py tests/unit/llm/test_openai.py
git commit -m "feat: Accept Azure AD token provider in AzureOpenAIClient"
```

---

### Task 6: Credential dispatch in `LLMFactory`

**Files:**
- Modify: `testbench_ai_service/llm/factory.py:44-64` (`get_client`) and `125-155` (`_create_client`), plus new helper methods
- Test: `tests/unit/llm/test_factory.py`

**Interfaces:**
- Consumes: `AzureAuthMethod` (Task 1), `resolve_entra_credentials` / `create_token_provider` / `EntraIdCredentials` (Tasks 3-4), the extended `AzureOpenAIClient` constructor (Task 5).
- Produces: `_uses_entra_id(provider, config) -> bool`, `_get_credential(provider, config) -> str | EntraIdCredentials | None`, `_get_project_credential(project_name, provider, config) -> str | EntraIdCredentials | None`, and `_create_client(provider, config, credential: str | EntraIdCredentials | None) -> LLMClient`. `_get_api_key` and `_get_project_api_key` keep their existing names and behaviour.

This task also fixes a latent bug on line 136: `_create_client` branches on `config.provider` instead of the resolved `provider` for the Azure case. With `provider = "azure_openai"` in config and a `claude-*` model in a prompt variant, `_resolve_provider` correctly returns `ANTHROPIC`, but `_create_client` then builds an Azure client anyway. The line is being edited here regardless, so it is corrected as part of the change and covered by a test.

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/llm/test_factory.py`. Extend the imports:

```python
from testbench_ai_service.llm.azure_auth import EntraIdCredentials
from testbench_ai_service.llm.base import AzureAuthMethod, LLMProvider
```

Extend the existing `_make_llm_config` helper so configs carry an auth method:

```python
def _make_llm_config(
    provider=LLMProvider.OPENAI,
    model="gpt-4o",
    auth_method=AzureAuthMethod.API_KEY,
):
    config = MagicMock()
    config.provider = provider
    config.model = model
    config.model_extra = {}
    config.azure_endpoint = None
    config.api_version = None
    config.auth_method = auth_method
    return config


def _make_azure_entra_config():
    config = _make_llm_config(
        provider=LLMProvider.AZURE_OPENAI,
        model="gpt-4o",
        auth_method=AzureAuthMethod.ENTRA_ID,
    )
    config.azure_endpoint = "https://example.openai.azure.com"
    config.api_version = "2024-10-21"
    return config
```

Append these test classes:

```python
class TestLLMFactoryEntraIdDispatch:
    """Entra ID mode must bypass the API key lookup entirely."""

    @patch.object(LLMFactory, "_create_client")
    @patch(
        "testbench_ai_service.llm.factory.resolve_entra_credentials",
        return_value=EntraIdCredentials(tenant_id="t", client_id="c", client_secret="s"),
    )
    @patch.object(LLMFactory, "_get_api_key", side_effect=AssertionError("must not be called"))
    def test_global_entra_client_does_not_look_up_an_api_key(
        self, mock_api_key, mock_resolve, mock_create
    ):
        factory = LLMFactory()
        config = _make_azure_entra_config()

        factory.get_client(config)

        mock_api_key.assert_not_called()
        mock_resolve.assert_called_once_with(None)
        assert mock_create.call_args.args[2] == EntraIdCredentials(
            tenant_id="t", client_id="c", client_secret="s"
        )

    @patch.object(LLMFactory, "_create_client")
    @patch("testbench_ai_service.llm.factory.resolve_entra_credentials")
    def test_project_principal_takes_precedence_over_global(self, mock_resolve, mock_create):
        project_credentials = EntraIdCredentials(
            tenant_id="tp", client_id="cp", client_secret="sp"
        )
        mock_resolve.return_value = project_credentials
        project_client = MagicMock()
        mock_create.return_value = project_client
        factory = LLMFactory()
        config = _make_azure_entra_config()

        result = factory.get_client(config, project_name="Car Configurator")

        assert result is project_client
        mock_resolve.assert_called_once_with("Car Configurator")
        assert mock_create.call_args.args[2] == project_credentials

    @patch.object(LLMFactory, "_create_client")
    @patch("testbench_ai_service.llm.factory.resolve_entra_credentials")
    def test_project_without_principal_falls_back_to_global_client(
        self, mock_resolve, mock_create
    ):
        global_credentials = EntraIdCredentials(tenant_id="t", client_id="c", client_secret="s")
        # First call is the project lookup (None), second is the global lookup.
        mock_resolve.side_effect = [None, global_credentials]
        global_client = MagicMock()
        mock_create.return_value = global_client
        factory = LLMFactory()
        config = _make_azure_entra_config()

        result = factory.get_client(config, project_name="Car Configurator")

        assert result is global_client
        assert mock_resolve.call_args_list == [call("Car Configurator"), call(None)]
        mock_create.assert_called_once()

    @patch.object(LLMFactory, "_create_client")
    @patch.object(LLMFactory, "_get_api_key", return_value="azure-key")
    @patch("testbench_ai_service.llm.factory.resolve_entra_credentials")
    def test_api_key_mode_does_not_resolve_entra_credentials(
        self, mock_resolve, mock_api_key, mock_create
    ):
        factory = LLMFactory()
        config = _make_llm_config(provider=LLMProvider.AZURE_OPENAI)
        config.azure_endpoint = "https://example.openai.azure.com"
        config.api_version = "2024-10-21"

        factory.get_client(config)

        mock_resolve.assert_not_called()
        mock_api_key.assert_called_once()


class TestLLMFactoryCreateAzureClient:
    # NOTE: this name must NOT collide with the pre-existing
    # `TestLLMFactoryCreateClient` class already in this file. A collision
    # silently shadows the older class so its tests stop being collected.
    @patch("testbench_ai_service.llm.factory.create_token_provider")
    @patch("testbench_ai_service.llm.factory.AzureOpenAIClient")
    def test_entra_credentials_produce_a_token_provider_client(
        self, mock_client_class, mock_token_provider
    ):
        credential = MagicMock(name="credential")
        provider_callable = MagicMock(name="provider")
        mock_token_provider.return_value = (credential, provider_callable)
        factory = LLMFactory()
        config = _make_azure_entra_config()

        factory._create_client(
            LLMProvider.AZURE_OPENAI,
            config,
            EntraIdCredentials(tenant_id="t", client_id="c", client_secret="s"),
        )

        kwargs = mock_client_class.call_args.kwargs
        assert kwargs["api_key"] is None
        assert kwargs["azure_ad_token_provider"] is provider_callable
        assert kwargs["credential"] is credential

    @patch("testbench_ai_service.llm.factory.AzureOpenAIClient")
    def test_string_credential_produces_an_api_key_client(self, mock_client_class):
        factory = LLMFactory()
        config = _make_llm_config(provider=LLMProvider.AZURE_OPENAI)
        config.azure_endpoint = "https://example.openai.azure.com"
        config.api_version = "2024-10-21"

        factory._create_client(LLMProvider.AZURE_OPENAI, config, "azure-key")

        kwargs = mock_client_class.call_args.kwargs
        assert kwargs["api_key"] == "azure-key"
        assert kwargs["azure_ad_token_provider"] is None
        assert kwargs["credential"] is None

    @patch("testbench_ai_service.llm.factory.AnthropicClient")
    def test_claude_model_on_azure_config_creates_an_anthropic_client(self, mock_anthropic):
        """Regression: the Azure branch must key off the resolved provider."""
        factory = LLMFactory()
        config = _make_llm_config(provider=LLMProvider.AZURE_OPENAI)
        config.azure_endpoint = "https://example.openai.azure.com"
        config.api_version = "2024-10-21"

        factory._create_client(LLMProvider.ANTHROPIC, config, "anthropic-key")

        mock_anthropic.assert_called_once()

    def test_entra_credentials_rejected_for_non_azure_provider(self):
        factory = LLMFactory()
        config = _make_llm_config(provider=LLMProvider.OPENAI)

        with pytest.raises(ValueError, match="azure_openai"):
            factory._create_client(
                LLMProvider.OPENAI,
                config,
                EntraIdCredentials(tenant_id="t", client_id="c", client_secret="s"),
            )


class TestLLMFactoryAuthLogging:
    @patch("testbench_ai_service.llm.factory.create_token_provider")
    @patch("testbench_ai_service.llm.factory.AzureOpenAIClient")
    def test_logs_entra_id_without_the_secret(self, mock_client, mock_token, caplog):
        mock_token.return_value = (MagicMock(), MagicMock())
        factory = LLMFactory()
        config = _make_azure_entra_config()

        with caplog.at_level("INFO", logger="testbench_ai_service"):
            factory._create_client(
                LLMProvider.AZURE_OPENAI,
                config,
                EntraIdCredentials(
                    tenant_id="tenant-1", client_id="client-1", client_secret="secret-value"
                ),
            )

        messages = [record.getMessage() for record in caplog.records]
        assert any("Entra ID" in message for message in messages)
        assert not any("secret-value" in message for message in messages)
```

Add `call` and `pytest` to the imports at the top of the file if they are not already there:

```python
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/llm/test_factory.py -v`
Expected: FAIL — `resolve_entra_credentials` cannot be patched on `testbench_ai_service.llm.factory` because it is not imported there yet.

- [ ] **Step 3: Wire the dispatch into the factory**

In `testbench_ai_service/llm/factory.py`, extend the imports:

```python
from testbench_ai_service.llm.azure_auth import (
    EntraIdCredentials,
    create_token_provider,
    resolve_entra_credentials,
)
from testbench_ai_service.llm.base import AzureAuthMethod, LLMClient, LLMProvider
from testbench_ai_service.log import logger
```

Replace the two credential lookups inside `get_client`. Line 53 becomes:

```python
            credential = self._get_project_credential(project_name, provider, config)
            if credential is not None:
                self._project_clients[key] = self._create_client(provider, config, credential)
                return self._project_clients[key]
```

and lines 60-62 become:

```python
        if provider not in self._clients:
            credential = self._get_credential(provider, config)
            self._clients[provider] = self._create_client(provider, config, credential)
```

Add these three helpers next to `_get_api_key`:

```python
    def _uses_entra_id(self, provider: LLMProvider, config: LLMConfig) -> bool:
        """
        Return True when this provider/config combination authenticates via Entra ID.
        """
        return (
            provider == LLMProvider.AZURE_OPENAI
            and config.auth_method == AzureAuthMethod.ENTRA_ID
        )

    def _get_credential(
        self, provider: LLMProvider, config: LLMConfig
    ) -> str | EntraIdCredentials | None:
        """
        Load the global credential for the provider: Entra ID credentials or an API key.
        """
        if self._uses_entra_id(provider, config):
            return resolve_entra_credentials(None)
        return self._get_api_key(provider)

    def _get_project_credential(
        self, project_name: str, provider: LLMProvider, config: LLMConfig
    ) -> str | EntraIdCredentials | None:
        """
        Load the project-specific credential, or None to fall back to the global one.
        """
        if self._uses_entra_id(provider, config):
            return resolve_entra_credentials(project_name)
        return self._get_project_api_key(project_name, provider)
```

Replace `_create_client` (lines 125-155) with:

```python
    def _create_client(
        self,
        provider: LLMProvider,
        config: LLMConfig,
        credential: str | EntraIdCredentials | None,
    ) -> LLMClient:
        """
        Create an LLM client instance using the given LLMConfig and credential.
        """
        common_kwargs = self._get_common_client_kwargs(config)

        if provider == LLMProvider.OPENAI:
            return OpenAIClient(api_key=self._as_api_key(credential), **common_kwargs)

        if provider == LLMProvider.AZURE_OPENAI:
            assert config.azure_endpoint is not None
            assert config.api_version is not None
            return self._create_azure_client(config, credential, common_kwargs)

        if provider == LLMProvider.ANTHROPIC:
            return AnthropicClient(api_key=self._as_api_key(credential), **common_kwargs)

        if provider == LLMProvider.CUSTOM:
            assert config.class_path is not None
            client_class: type[LLMClient] = load_class_from_path(config.class_path)
            return client_class(self._as_api_key(credential), **common_kwargs)

        raise NotImplementedError(f"Unsupported LLM provider: '{provider}'.")

    def _as_api_key(self, credential: str | EntraIdCredentials | None) -> str | None:
        """
        Narrow a credential to an API key, rejecting Entra ID credentials.
        """
        if isinstance(credential, EntraIdCredentials):
            raise ValueError(
                "Entra ID credentials are only supported for provider 'azure_openai'."
            )
        return credential

    def _create_azure_client(
        self,
        config: LLMConfig,
        credential: str | EntraIdCredentials | None,
        common_kwargs: dict[str, Any],
    ) -> LLMClient:
        """
        Create an Azure OpenAI client using either Entra ID or an API key.
        """
        api_key: str | None = None
        azure_credential = None
        token_provider = None

        if isinstance(credential, EntraIdCredentials):
            azure_credential, token_provider = create_token_provider(credential)
            logger.info(
                "Azure OpenAI client for endpoint '%s' authenticates via Entra ID "
                "(tenant '%s', client '%s').",
                config.azure_endpoint,
                credential.tenant_id,
                credential.client_id,
            )
        else:
            api_key = credential
            logger.info(
                "Azure OpenAI client for endpoint '%s' authenticates via API key.",
                config.azure_endpoint,
            )

        assert config.azure_endpoint is not None
        assert config.api_version is not None
        return AzureOpenAIClient(
            api_key=api_key,
            azure_endpoint=config.azure_endpoint,
            api_version=config.api_version,
            deployment_mapping=self._get_deployment_mapping(config),
            azure_ad_token_provider=token_provider,
            credential=azure_credential,
            **common_kwargs,
        )
```

Note that the Azure branch now tests the resolved `provider`, not `config.provider` — this is the bug fix described above.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/llm/ -v`
Expected: PASS, including every pre-existing factory test.

- [ ] **Step 5: Run the full suite and the type check**

Run: `.venv/Scripts/python.exe -m pytest -q && .venv/Scripts/python.exe -m mypy`
Expected: all tests pass, mypy reports no errors.

- [ ] **Step 6: Commit**

```bash
git add testbench_ai_service/llm/factory.py tests/unit/llm/test_factory.py
git commit -m "feat: Dispatch Azure credentials by auth method"
```

---

### Task 7: Documentation, example config and changelog

**Files:**
- Modify: `docs/llm-providers/azure-openai-setup.md`
- Modify: `config_example.toml:12-13`
- Modify: `CHANGELOG.md:7-9`

**Interfaces:**
- Consumes: the finished behaviour of Tasks 1-6.
- Produces: no code.

- [ ] **Step 1: Add the authentication section to the setup guide**

In `docs/llm-providers/azure-openai-setup.md`, replace section `## 3. Set the API key` with the following, and renumber nothing else — the surrounding sections keep their numbers:

````markdown
## 3. Choose an authentication method

The service supports two ways to authenticate against Azure OpenAI:

| Method | `auth_method` | When to use |
| --- | --- | --- |
| API key | `api_key` (default) | Direct integration scenarios where a key is explicitly required |
| Microsoft Entra ID | `entra_id` | Application development, and wherever your security policy mandates Entra ID |

Managed identity is not supported, because the service runs on-premise where no
managed identity is available. Entra ID authentication therefore uses a service
principal (app registration) with a client secret.

### Option A: API key

The service reads the Azure OpenAI API key from the environment variable
`AZURE_OPENAI_API_KEY`.

Create or update a `.env` file in the root of your installation directory:

```bash
# .env
AZURE_OPENAI_API_KEY=your_azure_openai_api_key
```

:::tip
Never commit API keys to version control. Add `.env` to your `.gitignore`.
:::

### Option B: Microsoft Entra ID

#### Prepare the app registration in Azure

These steps happen in your own Azure tenant and are your responsibility. The
AI service does not perform them.

1. In the [Azure portal](https://portal.azure.com), go to **Microsoft Entra ID**
   → **App registrations** → **New registration**. Give the application a name
   and register it.
2. On the application's **Overview** page, note the
   **Application (client) ID** and the **Directory (tenant) ID**.
3. Go to **Certificates & secrets** → **New client secret**. Note the secret
   **value** immediately; it is shown only once.
4. Open your **Azure OpenAI resource** → **Access control (IAM)** →
   **Add role assignment**. Assign the role
   **Cognitive Services OpenAI User** to the application you registered.

:::warning
Step 4 is the one that is most often missed. Without the role assignment the
configuration looks correct in every respect and every request still fails with
`401 Unauthorized` or `403 Forbidden`.
:::

#### Configure the service

Set `auth_method` in `config.toml`:

```toml
# config.toml
[testbench-ai-service.llm_config]
provider = "azure_openai"
auth_method = "entra_id"
azure_endpoint = "https://your-resource.openai.azure.com"
api_version = "2025-04-01-preview"
```

Supply the service principal through environment variables:

```bash
# .env
AZURE_TENANT_ID=your_directory_tenant_id
AZURE_CLIENT_ID=your_application_client_id
AZURE_CLIENT_SECRET=your_client_secret
```

| Variable | Azure portal name |
| --- | --- |
| `AZURE_TENANT_ID` | Directory (tenant) ID |
| `AZURE_CLIENT_ID` | Application (client) ID |
| `AZURE_CLIENT_SECRET` | Client secret **value** |

`AZURE_OPENAI_API_KEY` is not read in this mode and does not need to be set.

:::tip
Client secrets expire. Note the expiry date from **Certificates & secrets** and
plan the rotation — the service will start failing on the expiry date otherwise.
:::
````

- [ ] **Step 2: Document the per-project service principal**

In the same file, in the **Project-specific configuration** section, append after the paragraph describing `{NORMALIZED_PROJECT_NAME}_AZURE_OPENAI_API_KEY`:

````markdown
When `auth_method = "entra_id"` is configured, a project can likewise use its
own service principal. All three variables must be set together:

```bash
# .env
# For a project named "My Project":
MY_PROJECT_AZURE_TENANT_ID=project_specific_tenant_id
MY_PROJECT_AZURE_CLIENT_ID=project_specific_client_id
MY_PROJECT_AZURE_CLIENT_SECRET=project_specific_secret
```

If none of the three are set, the project uses the global service principal. If
only some are set, the service reports an error naming the missing variables
rather than falling back — a partially configured project principal would
otherwise authenticate silently as an unintended identity.

Note the timing differs by scope. Global credentials are validated when the
service starts, because the global client is created during startup. Project
credentials are resolved lazily, on the first request against that project, so
a partially configured project override does not stop the service from
starting.
````

- [ ] **Step 3: Add the troubleshooting rows**

Append these rows to the troubleshooting table at the end of the file:

```markdown
| `Entra ID authentication ... is incompletely configured` | One or two of the three service principal variables are missing | Set all of `AZURE_TENANT_ID`, `AZURE_CLIENT_ID` and `AZURE_CLIENT_SECRET` (or all three project-prefixed variants) |
| `'auth_method = entra_id' is only supported for provider 'azure_openai'` | `auth_method` set on a non-Azure provider | Remove `auth_method`, or set `provider = "azure_openai"` |
| `The 'azure-identity' package is required` | Running from source without the dependency installed | Run `pip install azure-identity` |
| `401 Unauthorized` / `403 Forbidden` with correct credentials | The app registration has no role on the Azure OpenAI resource | Assign the **Cognitive Services OpenAI User** role (step 4 above) |
| `ClientAuthenticationError: AADSTS7000215` | Invalid client secret, or the secret value was confused with the secret ID | Copy the secret **value** from **Certificates & secrets** |
| `ClientAuthenticationError` after months of working | The client secret expired | Create a new secret and update `AZURE_CLIENT_SECRET` |
```

- [ ] **Step 4: Update the example config**

In `config_example.toml`, replace lines 12-13 with:

```toml
[testbench-ai-service.llm_config]
provider = "openai"
# Authentication method for provider "azure_openai": "api_key" (default) or "entra_id".
# With "entra_id", set AZURE_TENANT_ID, AZURE_CLIENT_ID and AZURE_CLIENT_SECRET
# instead of AZURE_OPENAI_API_KEY.
# auth_method = "api_key"
```

- [ ] **Step 5: Update the changelog**

In `CHANGELOG.md`, insert directly above the `## [1.0.1][1.0.1] - 2026-06-29` heading:

```markdown
## [Unreleased]

### Added

- Microsoft Entra ID authentication for Azure OpenAI via a service principal, selected with `auth_method = "entra_id"` in `llm_config`. Credentials are read from `AZURE_TENANT_ID`, `AZURE_CLIENT_ID` and `AZURE_CLIENT_SECRET`, with per-project overrides using the `{PROJECT}_` prefix.

### Fixed

- Azure OpenAI client creation no longer overrides the provider resolved from the model name, so a `claude-*` model in a prompt variant correctly creates an Anthropic client even when `provider = "azure_openai"` is configured.

```

- [ ] **Step 6: Verify the documented values against the code**

This step catches drift between the docs and the implementation. Confirm each of these by reading the source, not from memory:

- The three environment variable names in the docs match `_ENV_SUFFIXES` in `testbench_ai_service/llm/azure_auth.py`.
- The `auth_method` values in the docs match the members of `AzureAuthMethod` in `testbench_ai_service/llm/base.py`.
- The error message strings quoted in the troubleshooting table match the strings raised in `azure_auth.py` and `models/config.py`.

- [ ] **Step 7: Run the full suite one last time**

Run: `.venv/Scripts/python.exe -m pytest -q && .venv/Scripts/python.exe -m mypy`
Expected: all tests pass, mypy reports no errors.

- [ ] **Step 8: Commit**

```bash
git add docs/llm-providers/azure-openai-setup.md config_example.toml CHANGELOG.md
git commit -m "docs: Document Entra ID authentication for Azure OpenAI"
```

---

## Manual verification against a real Azure resource

The automated tests are fully mocked, so one manual pass is needed before the
story is done. This requires an Azure OpenAI resource and an app registration.

- [ ] Configure `auth_method = "entra_id"` with the three environment variables set and `AZURE_OPENAI_API_KEY` **unset**. Start the service and run one agent request. Expect success, and an `info` log line naming Entra ID.
- [ ] Grep the log file for the client secret value. Expect no match.
- [ ] Unset `AZURE_CLIENT_SECRET` and restart. Expect an error naming that variable.
- [ ] Remove the **Cognitive Services OpenAI User** role assignment and run a request. Expect a 401/403 whose log line identifies the tenant and client.
- [ ] Revert to `auth_method = "api_key"` with `AZURE_OPENAI_API_KEY` set. Expect unchanged behaviour.
- [ ] Build the binary with `python build_binary.py` and repeat the first check against `dist/testbench-ai-service/`. This is the check that catches missing PyInstaller hidden imports; it cannot be caught by any test run from source.
