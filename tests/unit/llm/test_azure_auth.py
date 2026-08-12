import builtins
import sys
from unittest.mock import MagicMock

import pytest

from testbench_ai_service.llm.azure_auth import (
    AZURE_TOKEN_SCOPE,
    EntraIdCredentials,
    create_token_provider,
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
        with pytest.raises(ValueError, match="Missing environment variable") as exc_info:
            resolve_entra_credentials()
        message = str(exc_info.value)
        for name in GLOBAL_VARS:
            assert name in message

    @pytest.mark.parametrize("missing", GLOBAL_VARS)
    def test_raises_and_names_the_missing_variable(self, monkeypatch, missing):
        for name in GLOBAL_VARS:
            if name != missing:
                monkeypatch.setenv(name, "value")

        with pytest.raises(ValueError, match="Missing environment variable") as exc_info:
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

        with pytest.raises(ValueError, match="Missing environment variable") as exc_info:
            resolve_entra_credentials("Car Configurator")

        message = str(exc_info.value)
        assert "Car Configurator" in message
        for name in PROJECT_VARS:
            if name != present:
                assert name in message

    def test_secret_value_is_not_in_the_error_message(self, monkeypatch):
        monkeypatch.setenv("CAR_CONFIGURATOR_AZURE_CLIENT_SECRET", "super-secret-value")

        with pytest.raises(ValueError, match="Missing environment variable") as exc_info:
            resolve_entra_credentials("Car Configurator")

        assert "super-secret-value" not in str(exc_info.value)


def _block_azure_identity_aio_import(monkeypatch):
    """Make `import azure.identity.aio` fail with ImportError, as if the package were absent."""
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "azure.identity.aio":
            raise ImportError("No module named 'azure'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)


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
        _block_azure_identity_aio_import(monkeypatch)

        with pytest.raises(ValueError, match="azure-identity"):
            create_token_provider(
                EntraIdCredentials(tenant_id="t", client_id="c", client_secret="s")
            )

    def test_secret_is_not_in_the_import_error_message(self, monkeypatch):
        _block_azure_identity_aio_import(monkeypatch)

        with pytest.raises(ValueError, match="azure-identity") as exc_info:
            create_token_provider(
                EntraIdCredentials(
                    tenant_id="t", client_id="c", client_secret="super-secret-value"
                )
            )

        assert "super-secret-value" not in str(exc_info.value)
