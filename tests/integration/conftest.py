from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from testbench_ai_service.auth import validate_session_token
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
    cfg = AppConfig(tb_server_url=TB_SERVER_URL)
    application = create_app(cfg)

    mock_llm_client = AsyncMock()
    mock_llm_client.query_llm = AsyncMock(return_value="No review notes")
    mock_llm_factory = MagicMock()
    mock_llm_factory.get_client.return_value = mock_llm_client

    application.dependency_overrides[validate_session_token] = lambda: "test-session-token"
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
        payload = {"project_key": PROJECT_KEY, "tov_key": TOV_KEY, **extra_fields}
        return client.post(endpoint, json=payload)

    return _post
