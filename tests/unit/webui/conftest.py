from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from testbench_ai_service.config import AppConfig
from testbench_ai_service.main import create_app

TB_URL = "https://localhost:9443/api/"


@pytest.fixture
def make_app():
    """Build a real app with the LLM factory mocked out."""

    def _make(**config_kwargs):
        with (
            patch("testbench_ai_service.config.validate_tb_server_url"),
            patch("testbench_ai_service.main.LLMFactory") as factory_cls,
        ):
            instance = MagicMock()
            instance.init_clients = MagicMock()
            instance.close_clients = AsyncMock()
            factory_cls.return_value = instance
            return create_app(AppConfig(tb_server_url=TB_URL, **config_kwargs))

    return _make


@pytest.fixture
def app(make_app):
    return make_app()


@pytest.fixture
def client(app):
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def tb_connection():
    """A stand-in for testbench_cli_reporter's Connection."""
    conn = MagicMock()
    conn.session_token = "tb-token-abc"
    conn.read_user_roles.return_value = ["Administrator"]
    conn.session = MagicMock()
    # The login also reads the project list from this connection. An explicit
    # empty answer rather than the default MagicMock, so tests that do not care
    # about projects get a realistic payload instead of an unparseable one.
    conn.get_all_projects.return_value = {"projects": []}
    return conn


@pytest.fixture
def login(client, tb_connection):
    """Log in and return the response, with TestBench mocked."""

    def _login(username="a.mueller", password="pw", roles=None):
        if roles is not None:
            tb_connection.read_user_roles.return_value = roles
        with patch("testbench_ai_service.webui.auth.TBConnection", return_value=tb_connection):
            return client.post(
                "/admin/api/session", json={"username": username, "password": password}
            )

    return _login
