from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from testbench_ai_service.auth import AuthInfo, AuthType, validate_auth_token
from testbench_ai_service.config import AppConfig
from testbench_ai_service.dependencies import get_llm_factory, get_tb_connection
from testbench_ai_service.main import create_app

PROJECT_KEY = "1"
TOV_KEY = "2"
CYCLE_KEY = "3"
USER_KEY = "0"
PROJECT_NAME = "Car Configurator"
TB_SERVER_URL = "https://localhost:9443/api/"


@pytest.fixture
def app():
    """FastAPI app instance with all external dependencies mocked out."""
    with (
        patch("testbench_ai_service.config.validate_tb_server_url"),
        patch("testbench_ai_service.main.LLMFactory") as mock_factory_cls,
    ):
        mock_llm_client = AsyncMock()
        mock_llm_client.query_llm = AsyncMock(return_value="No review notes")
        mock_llm_factory = MagicMock()
        mock_llm_factory.get_client.return_value = mock_llm_client

        mock_factory_instance = MagicMock()
        mock_factory_instance.init_clients = MagicMock()
        mock_factory_instance.close_clients = AsyncMock()
        mock_factory_instance.get_client.return_value = mock_llm_client
        mock_factory_cls.return_value = mock_factory_instance

        cfg = AppConfig(tb_server_url=TB_SERVER_URL)
        application = create_app(cfg)

    application.dependency_overrides[validate_auth_token] = lambda: AuthInfo(
        auth_type=AuthType.SESSION_TOKEN,
        token="test-session-token",
        user_key=USER_KEY,
        conn=MagicMock(),
    )
    application.dependency_overrides[get_tb_connection] = lambda: MagicMock(
        server_url=TB_SERVER_URL
    )
    application.dependency_overrides[get_llm_factory] = lambda: mock_llm_factory

    yield application

    application.dependency_overrides.clear()


@pytest.fixture
def client(app):
    """HTTP test client bound to the mocked app."""
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def post(client):
    """Convenience callable for POSTing to use-case endpoints.

    Always includes the minimum required ``project_key`` and ``tov_key`` fields.
    Pass additional fields as keyword arguments.

    Usage::

        response = post("/test-case-set-reviews", cycle_key="3")
    """

    def _post(endpoint: str, **extra_fields):
        payload = {
            "project_key": PROJECT_KEY,
            "tov_key": TOV_KEY,
            "element_type": "TESTCASESET",
            "root_uid": "iTB-TC-66",
            **extra_fields,
        }
        return client.post(endpoint, json=payload)

    return _post
