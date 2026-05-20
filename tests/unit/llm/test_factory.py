from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from testbench_ai_service.llm.base import LLMProvider
from testbench_ai_service.llm.factory import LLMFactory


def _make_llm_config(provider=LLMProvider.OPENAI, model="gpt-4o"):
    config = MagicMock()
    config.provider = provider
    config.model = model
    config.model_extra = {}
    config.azure_endpoint = None
    config.api_version = None
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


class TestLLMFactoryCreateClient:
    @patch("testbench_ai_service.llm.factory.AzureOpenAIClient")
    def test_creates_azure_openai_client(self, mock_azure_client_class):
        config = _make_llm_config(provider=LLMProvider.AZURE_OPENAI)
        config.azure_endpoint = "https://example.openai.azure.com"
        config.api_version = "2024-10-21"
        config.model_extra = {
            "deployment_mapping": {"azure-gpt-4o-prod": "gpt-4o"},
        }

        factory = LLMFactory()
        client = factory._create_client(LLMProvider.AZURE_OPENAI, config, api_key="azure-key")

        assert client is mock_azure_client_class.return_value
        mock_azure_client_class.assert_called_once_with(
            api_key="azure-key",
            azure_endpoint="https://example.openai.azure.com",
            api_version="2024-10-21",
            deployment_mapping={"azure-gpt-4o-prod": "gpt-4o"},
        )

    def test_invalid_deployment_mapping_raises_value_error(self):
        config = _make_llm_config(provider=LLMProvider.AZURE_OPENAI)
        config.azure_endpoint = "https://example.openai.azure.com"
        config.api_version = "2024-10-21"
        config.model_extra = {"deployment_mapping": ["invalid"]}

        factory = LLMFactory()

        with pytest.raises(ValueError, match=r"'deployment_mapping' must be a dictionary"):
            factory._create_client(LLMProvider.AZURE_OPENAI, config, api_key="azure-key")


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
