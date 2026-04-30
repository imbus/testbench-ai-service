import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from testbench_ai_service.auth import AuthInfo, AuthType, get_auth_info
from testbench_ai_service.config import AppConfig
from testbench_ai_service.dependencies import get_app_config
from testbench_ai_service.main import create_app


def _make_auth_info() -> AuthInfo:
    return AuthInfo(auth_type=AuthType.SESSION_TOKEN, token="valid-token", user_key="user1")


def _make_test_client():
    """Spin up a TestClient with a real AppConfig and patched auth."""
    app_config = AppConfig(tb_server_url="https://localhost:9443/api/")
    app = create_app(app_config)
    client = TestClient(app, follow_redirects=False)
    client.__enter__()

    app.dependency_overrides[get_auth_info] = _make_auth_info
    app.dependency_overrides[get_app_config] = lambda: app_config

    return client, app, app_config


@patch("testbench_ai_service.main.LLMFactory")
class TestRootRedirect(unittest.TestCase):
    def test_root_redirects_to_docs(self, mock_factory_cls):
        mock_factory = MagicMock()
        mock_factory.init_clients = MagicMock()
        mock_factory.close_clients = MagicMock()
        mock_factory_cls.return_value = mock_factory

        client, _, _ = _make_test_client()
        response = client.get("/")

        # 307 redirect toward /docs
        self.assertIn(response.status_code, (301, 302, 307, 308))
        self.assertIn("docs", response.headers.get("location", ""))


@patch("testbench_ai_service.main.LLMFactory")
class TestGetUsecases(unittest.TestCase):
    def setUp(self):
        self.mock_factory = MagicMock()
        self.mock_factory.init_clients = MagicMock()
        self.mock_factory.close_clients = MagicMock()

    def _client(self, mock_factory_cls):
        mock_factory_cls.return_value = self.mock_factory
        return _make_test_client()

    def test_returns_all_usecases_by_default(self, mock_factory_cls):
        client, _, _ = self._client(mock_factory_cls)
        response = client.get("/usecases")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        keys = [item["key"] for item in data]
        self.assertIn("test_case_set_reviews", keys)
        self.assertIn("test_case_set_descriptions", keys)
        self.assertIn("defect_explanations", keys)

    def test_filter_by_enabled_true(self, mock_factory_cls):
        client, _, _ = self._client(mock_factory_cls)
        response = client.get("/usecases?enabled=true")
        self.assertEqual(response.status_code, 200)
        for item in response.json():
            self.assertTrue(item["enabled"])

    def test_filter_by_enabled_false_returns_empty(self, mock_factory_cls):
        """All default usecases are enabled, so filtering by enabled=false yields empty list."""
        client, _, _ = self._client(mock_factory_cls)
        response = client.get("/usecases?enabled=false")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_requires_auth_token(self, mock_factory_cls):
        """Without a session token the endpoint must return 401."""
        mock_factory_cls.return_value = self.mock_factory
        app_config = AppConfig(tb_server_url="https://localhost:9443/api/")
        app = create_app(app_config)
        client = TestClient(app, follow_redirects=False)
        client.__enter__()
        # No dependency override — real auth will reject the empty token
        response = client.get("/usecases")
        self.assertIn(response.status_code, (401, 403))


@patch("testbench_ai_service.main.LLMFactory")
class TestGetPromptDetails(unittest.TestCase):
    def setUp(self):
        self.mock_factory = MagicMock()
        self.mock_factory.init_clients = MagicMock()
        self.mock_factory.close_clients = MagicMock()

    def _client(self, mock_factory_cls):
        mock_factory_cls.return_value = self.mock_factory
        return _make_test_client()

    def test_returns_prompt_details_for_known_usecase(self, mock_factory_cls):
        client, _, _ = self._client(mock_factory_cls)
        response = client.get("/usecases/test_case_set_reviews/prompt")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("name", data)
        self.assertIn("variants", data)
        self.assertIsInstance(data["variants"], list)

    def test_returns_404_for_unknown_usecase(self, mock_factory_cls):
        client, _, _ = self._client(mock_factory_cls)
        response = client.get("/usecases/nonexistent_usecase/prompt")
        self.assertEqual(response.status_code, 404)

    def test_requires_auth_for_prompt_details(self, mock_factory_cls):
        mock_factory_cls.return_value = self.mock_factory
        app_config = AppConfig(tb_server_url="https://localhost:9443/api/")
        app = create_app(app_config)
        client = TestClient(app, follow_redirects=False)
        client.__enter__()
        response = client.get("/usecases/test_case_set_reviews/prompt")
        self.assertIn(response.status_code, (401, 403))


if __name__ == "__main__":
    unittest.main()
