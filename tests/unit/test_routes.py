import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests
from fastapi import HTTPException
from fastapi.testclient import TestClient

from testbench_ai_service.agent_packages import loaded
from testbench_ai_service.agent_packages.manifest import site_dir
from testbench_ai_service.agents.routes import get_agent_routers, load_agent
from testbench_ai_service.auth import AuthInfo, AuthType, validate_auth_token
from testbench_ai_service.config import DEFAULT_AGENTS, AppConfig
from testbench_ai_service.dependencies import get_app_config
from testbench_ai_service.main import create_app
from testbench_ai_service.models.config import AgentConfig, PromptConfig
from testbench_ai_service.routes import _resolve_project_name
from tests.helpers.packages import (
    BROKEN_CLASS_PATH,
    CLASS_PATH,
    PACKAGE,
    install_package,
    install_two_agent_package,
)


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
    def test_root_redirects_to_console(self):
        client, _, _ = _make_test_client()
        response = client.get("/")
        assert response.status_code in (301, 302, 307, 308)
        assert response.headers.get("location") == "/admin/"


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


class TestResolveProjectName:
    """``_resolve_project_name`` must map transport failures to HTTP 502."""

    @patch("testbench_ai_service.routes.get_project_name", return_value="Car Configurator")
    def test_returns_project_name(self, mock_get_project_name):
        assert _resolve_project_name(MagicMock(), "1") == "Car Configurator"

    def test_returns_none_without_project_key(self):
        assert _resolve_project_name(MagicMock(), None) is None

    @patch(
        "testbench_ai_service.routes.get_project_name",
        side_effect=requests.exceptions.ConnectionError("Connection refused"),
    )
    def test_connection_error_raises_502(self, mock_get_project_name):
        with pytest.raises(HTTPException) as exc_info:
            _resolve_project_name(MagicMock(), "1")
        assert exc_info.value.status_code == 502

    @patch(
        "testbench_ai_service.routes.get_project_name",
        side_effect=requests.exceptions.ReadTimeout("Read timed out."),
    )
    def test_read_timeout_raises_502(self, mock_get_project_name):
        with pytest.raises(HTTPException) as exc_info:
            _resolve_project_name(MagicMock(), "1")
        assert exc_info.value.status_code == 502


class TestPackageAgentRouters:
    @staticmethod
    def _config(packages_dir: Path, class_path: str = CLASS_PATH) -> AppConfig:
        prompt = site_dir(packages_dir, PACKAGE, "1.0.0") / "acme/rater/prompts/en/prompt.yaml"
        agent = AgentConfig(
            enabled=True,
            endpoint_path="/acme",
            class_path=class_path,
            prompt=PromptConfig(file=prompt),
            package=PACKAGE,
        )
        with patch("testbench_ai_service.config.validate_tb_server_url"):
            return AppConfig(
                tb_server_url="https://localhost:9443/api/",
                agents={**DEFAULT_AGENTS, "acme": agent},
                agent_packages={"dir": packages_dir},
            )

    @staticmethod
    def _paths(routers) -> set[str]:
        return {route.path for router in routers for route in router.routes}

    def test_routers_skip_unloaded_package_agent(self, tmp_path):
        install_package(tmp_path)
        config = self._config(tmp_path)

        paths = self._paths(get_agent_routers(config))

        assert "/acme" not in paths
        assert "/test-case-set-reviews" in paths
        assert "acme" not in sys.modules

    def test_routers_include_loaded_package_agent(self, tmp_path):
        install_package(tmp_path)
        loaded.activate_packages(tmp_path)
        config = self._config(tmp_path)

        assert "/acme" in self._paths(get_agent_routers(config))

    def test_routers_skip_only_the_package_agent_whose_import_fails(self, tmp_path):
        install_two_agent_package(tmp_path)
        loaded.activate_packages(tmp_path)
        config = self._config(tmp_path)
        broken = config.agents["acme"].model_copy(
            update={"class_path": BROKEN_CLASS_PATH, "endpoint_path": "/broken"}
        )
        config.agents["acme_broken"] = broken

        paths = self._paths(get_agent_routers(config))

        assert "/acme" in paths
        assert "/broken" not in paths
        assert set(loaded.agent_failures()) == {"acme_broken"}
        assert "SystemExit" in loaded.agent_failures()["acme_broken"]
        assert loaded.is_loaded(PACKAGE)
        assert loaded.failures() == {}


class TestLoadPackageAgent:
    @staticmethod
    def _agent(class_path: str = CLASS_PATH, **kwargs) -> AgentConfig:
        return AgentConfig(
            enabled=True,
            endpoint_path="/acme",
            class_path=class_path,
            prompt=PromptConfig(file=Path("acme/prompt.yaml")),
            package=PACKAGE,
            **kwargs,
        )

    def test_loads_an_agent_of_a_loaded_package(self, tmp_path):
        install_package(tmp_path)
        loaded.activate_packages(tmp_path)

        assert type(load_agent(self._agent(), "acme")).__name__ == "RaterAgent"

    def test_refuses_an_agent_of_a_package_that_is_not_loaded(self, tmp_path):
        install_package(tmp_path)

        with pytest.raises(HTTPException) as exc_info:
            load_agent(self._agent(), "acme")

        assert exc_info.value.status_code == 503
        assert "acme" not in sys.modules

    def test_refuses_an_agent_that_failed_at_startup(self, tmp_path):
        install_package(tmp_path)
        loaded.activate_packages(tmp_path)
        loaded.mark_agent_failed("acme", "boom")

        with pytest.raises(HTTPException) as exc_info:
            load_agent(self._agent(), "acme")

        assert exc_info.value.status_code == 503
        assert "boom" in exc_info.value.detail

    def test_refuses_an_agent_whose_import_exits(self, tmp_path):
        install_two_agent_package(tmp_path)
        loaded.activate_packages(tmp_path)

        with pytest.raises(HTTPException) as exc_info:
            load_agent(self._agent(BROKEN_CLASS_PATH), "acme_broken")

        assert exc_info.value.status_code == 503

    def test_refuses_invalid_args_with_503(self, tmp_path):
        install_package(tmp_path)
        loaded.activate_packages(tmp_path)

        with pytest.raises(HTTPException) as exc_info:
            load_agent(self._agent(args={"typo": 1}), "acme")

        assert exc_info.value.status_code == 503
        assert "typo" in exc_info.value.detail
