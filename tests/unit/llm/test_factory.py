import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from testbench_ai_service.llm.base import LLMProvider
from testbench_ai_service.llm.factory import LLMFactory


def _make_llm_config(provider=LLMProvider.OPENAI, model="gpt-4o"):
    config = MagicMock()
    config.provider = provider
    config.model = model
    return config


class TestLLMFactoryGetClient(unittest.TestCase):
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
        self.assertIs(result, mock_client)

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
        self.assertIs(first, second)
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
        self.assertIs(result, project_client)

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
        self.assertIs(result, global_client)


class TestLLMFactoryInitClients(unittest.TestCase):
    """Tests for ``LLMFactory.init_clients``."""

    @patch.object(LLMFactory, "get_client")
    def test_calls_get_client_for_each_config(self, mock_get_client):
        factory = LLMFactory()
        configs = [_make_llm_config(), _make_llm_config(provider=LLMProvider.CUSTOM)]
        factory.init_clients(configs)
        self.assertEqual(mock_get_client.call_count, len(configs))


class TestLLMFactoryCloseClients(unittest.IsolatedAsyncioTestCase):
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


if __name__ == "__main__":
    unittest.main()
