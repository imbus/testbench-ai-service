from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from testbench_ai_service.llm.azure_auth import EntraIdCredentials
from testbench_ai_service.llm.base import AzureAuthMethod, LLMProvider
from testbench_ai_service.llm.factory import LLMFactory


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


class TestLLMFactoryGetClient:
    """Tests for ``LLMFactory.get_client``."""

    @patch.object(LLMFactory, "_create_client")
    @patch.object(LLMFactory, "_get_api_key", return_value="test-key")
    def test_returns_global_client_for_known_provider(self, mock_key, mock_create):
        mock_key.return_value = "test-key"
        mock_client = MagicMock()
        mock_create.return_value = mock_client
        factory = LLMFactory()
        config = _make_llm_config()
        result = factory.get_client(config)
        assert result is mock_client

    @patch.object(LLMFactory, "_create_client")
    @patch.object(LLMFactory, "_get_api_key", return_value="test-key")
    def test_same_instance_returned_on_second_call(self, mock_key, mock_create):
        mock_key.return_value = "test-key"
        mock_client = MagicMock()
        mock_create.return_value = mock_client
        factory = LLMFactory()
        config = _make_llm_config()
        first = factory.get_client(config)
        second = factory.get_client(config)
        assert first is second
        mock_create.assert_called_once()

    @patch.object(LLMFactory, "_create_client")
    @patch.object(LLMFactory, "_get_project_api_key", return_value="proj-key")
    @patch.object(LLMFactory, "_get_api_key", return_value="global-key")
    def test_creates_project_specific_client_when_project_key_exists(
        self, mock_global_key, mock_proj_key, mock_create
    ):
        mock_global_key.return_value = "global-key"
        mock_proj_key.return_value = "proj-key"
        project_client = MagicMock()
        mock_create.return_value = project_client
        factory = LLMFactory()
        config = _make_llm_config()
        result = factory.get_client(config, project_name="ProjectAlpha")
        assert result is project_client

    @patch.object(LLMFactory, "_create_client")
    @patch.object(LLMFactory, "_get_project_api_key")
    @patch.object(LLMFactory, "_get_api_key")
    def test_falls_back_to_global_client_when_no_project_key(
        self, mock_global_key, mock_proj_key, mock_create
    ):
        mock_global_key.return_value = "global-key"
        mock_proj_key.return_value = None
        global_client = MagicMock()
        mock_create.return_value = global_client
        factory = LLMFactory()
        config = _make_llm_config()
        result = factory.get_client(config, project_name="Unknown")
        assert result is global_client


class TestLLMFactoryInitClients:
    """Tests for ``LLMFactory.init_clients``."""

    @patch.object(LLMFactory, "get_client")
    def test_calls_get_client_for_each_config(self, mock_get_client):
        factory = LLMFactory()
        configs = [_make_llm_config(), _make_llm_config(provider=LLMProvider.CUSTOM)]
        factory.init_clients(configs)
        assert mock_get_client.call_count == len(configs)


class TestLLMFactoryCloseClients:
    """Tests for ``LLMFactory.close_clients``."""

    async def test_closes_all_cached_clients(self):
        factory = LLMFactory()
        client_a = AsyncMock()
        client_b = AsyncMock()
        factory._clients[LLMProvider.OPENAI] = client_a
        factory._project_clients[("ProjectA", LLMProvider.OPENAI)] = client_b
        await factory.close_clients()
        client_a.close.assert_awaited_once()
        client_b.close.assert_awaited_once()


class TestLLMFactoryResolveProvider:
    """Tests for ``LLMFactory._resolve_provider``."""

    def _make_config(self, provider: LLMProvider):
        config = MagicMock()
        config.provider = provider
        return config

    def test_gpt_model_with_openai_config_returns_openai(self):
        factory = LLMFactory()
        config = self._make_config(LLMProvider.OPENAI)
        assert factory._resolve_provider(config, "gpt-4o") == LLMProvider.OPENAI

    def test_gpt_model_with_azure_config_returns_azure(self):
        factory = LLMFactory()
        config = self._make_config(LLMProvider.AZURE_OPENAI)
        assert factory._resolve_provider(config, "gpt-4o") == LLMProvider.AZURE_OPENAI

    @pytest.mark.parametrize("model", ["o1", "o3", "o4-mini", "o1-preview", "o3-deep-research"])
    def test_o_series_model_with_openai_config_returns_openai(self, model):
        factory = LLMFactory()
        config = self._make_config(LLMProvider.OPENAI)
        assert factory._resolve_provider(config, model) == LLMProvider.OPENAI

    @pytest.mark.parametrize("model", ["o1", "o4-mini"])
    def test_o_series_model_with_azure_config_returns_azure(self, model):
        factory = LLMFactory()
        config = self._make_config(LLMProvider.AZURE_OPENAI)
        assert factory._resolve_provider(config, model) == LLMProvider.AZURE_OPENAI

    def test_claude_model_returns_anthropic(self):
        factory = LLMFactory()
        config = self._make_config(LLMProvider.OPENAI)
        assert factory._resolve_provider(config, "claude-3-sonnet") == LLMProvider.ANTHROPIC

    def test_none_model_returns_config_provider(self):
        factory = LLMFactory()
        config = self._make_config(LLMProvider.ANTHROPIC)
        assert factory._resolve_provider(config, None) == LLMProvider.ANTHROPIC

    def test_openai_model_with_non_openai_config_falls_back_to_openai(self):
        factory = LLMFactory()
        config = self._make_config(LLMProvider.ANTHROPIC)
        assert factory._resolve_provider(config, "gpt-4o") == LLMProvider.OPENAI

    @pytest.mark.parametrize("model", ["ollama-llama3", "openhermes"])
    def test_non_openai_model_names_not_matched_as_openai(self, model):
        factory = LLMFactory()
        assert not factory._is_openai_model(model)


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


class TestLLMFactoryCreateClient:
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
