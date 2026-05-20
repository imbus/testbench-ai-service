from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from testbench_ai_service.auth import AuthInfo, AuthType, validate_auth_token
from testbench_ai_service.config import AppConfig
from testbench_ai_service.dependencies import get_app_config
from testbench_ai_service.main import create_app


def _make_auth_info() -> AuthInfo:
    return AuthInfo(
        auth_type=AuthType.SESSION_TOKEN,
        token="valid-token",
        user_key="user1",
        conn=MagicMock(),
    )


def _make_app_config():
    with patch("testbench_ai_service.config.validate_tb_server_url"):
        return AppConfig(tb_server_url="https://localhost:9443/api/")


def _make_test_client():
    app_config = _make_app_config()
    with patch("testbench_ai_service.main.LLMFactory") as mock_factory_cls:
        mock_factory = MagicMock()
        mock_factory.init_clients = MagicMock()
        mock_factory.close_clients = MagicMock()
        mock_factory_cls.return_value = mock_factory
        app = create_app(app_config)

    client = TestClient(app, follow_redirects=False)
    client.__enter__()
    app.dependency_overrides[validate_auth_token] = _make_auth_info
    app.dependency_overrides[get_app_config] = lambda: app_config
    return client, app, app_config


def _make_unauthenticated_client():
    """Returns a test client with no auth override (real auth validation runs)."""
    app_config = _make_app_config()
    with patch("testbench_ai_service.main.LLMFactory") as mock_factory_cls:
        mock_factory = MagicMock()
        mock_factory.init_clients = MagicMock()
        mock_factory.close_clients = MagicMock()
        mock_factory_cls.return_value = mock_factory
        app = create_app(app_config)
    client = TestClient(app, follow_redirects=False)
    client.__enter__()
    return client


class TestRootRedirect:
    def test_root_redirects_to_docs(self):
        client, _, _ = _make_test_client()
        response = client.get("/")
        assert response.status_code in (301, 302, 307, 308)
        assert "docs" in response.headers.get("location", "")


class TestGetAgents:
    def test_returns_all_agents_by_default(self):
        client, _, _ = _make_test_client()
        response = client.get("/agents")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        keys = [item["key"] for item in data]
        assert "test_case_set_reviewer" in keys
        assert "test_case_set_describer" in keys
        assert "defect_explainer" in keys

    def test_filter_by_enabled_true(self):
        client, _, _ = _make_test_client()
        response = client.get("/agents?enabled=true")
        assert response.status_code == 200
        for item in response.json():
            assert item["enabled"]

    def test_filter_by_enabled_false_returns_empty(self):
        client, _, _ = _make_test_client()
        response = client.get("/agents?enabled=false")
        assert response.status_code == 200
        assert response.json() == []

    def test_requires_auth_token(self):
        client = _make_unauthenticated_client()
        response = client.get("/agents")
        assert response.status_code in (401, 403)


class TestGetPromptDetails:
    def test_returns_prompt_details_for_known_agent(self):
        client, _, _ = _make_test_client()
        response = client.get("/agents/test_case_set_reviewer/prompt")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "variants" in data
        assert isinstance(data["variants"], list)

    def test_returns_404_for_unknown_agent(self):
        client, _, _ = _make_test_client()
        response = client.get("/agents/nonexistent_agent/prompt")
        assert response.status_code == 404

    def test_requires_auth_for_prompt_details(self):
        client = _make_unauthenticated_client()
        response = client.get("/agents/test_case_set_reviewer/prompt")
        assert response.status_code in (401, 403)
