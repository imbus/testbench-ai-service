from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from testbench_ai_service.auth import AuthInfo, AuthType, validate_auth_token
from testbench_ai_service.config import AppConfig
from testbench_ai_service.main import create_app

TB_URL = "https://localhost:9443/api/"


def _auth_info() -> AuthInfo:
    return AuthInfo(
        auth_type=AuthType.SESSION_TOKEN, token="test-token", user_key="1", conn=MagicMock()
    )


@pytest.fixture
def app():
    with (
        patch("testbench_ai_service.config.validate_tb_server_url"),
        patch("testbench_ai_service.main.LLMFactory") as factory_cls,
    ):
        factory = MagicMock()
        factory.close_clients = AsyncMock()
        factory_cls.return_value = factory
        return create_app(AppConfig(tb_server_url=TB_URL))


@pytest.fixture
def client(app):
    app.dependency_overrides[validate_auth_token] = _auth_info
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def store(app):
    return app.state.job_store


def _create(store, job_id: str, user_key: str) -> None:
    store.create(
        job_id,
        agent_key="coverage_checker",
        user_key=user_key,
        project_key="p",
        project_name="P",
        root_key=None,
        item_ids=["i1"],
        warnings=[],
    )


def test_own_job_returns_detail_with_report(client, store):
    _create(store, "j1", "1")
    store.set_report("j1", "coverage_checker", {"a": 1})
    r = client.get("/jobs/j1")
    assert r.status_code == 200
    assert r.json()["report"] == {"a": 1}
    assert r.json()["job_id"] == "j1"


def test_foreign_job_returns_404(client, store):
    _create(store, "j1", "2")
    assert client.get("/jobs/j1").status_code == 404


def test_foreign_and_unknown_jobs_are_indistinguishable(client, store):
    _create(store, "j1", "2")
    foreign, unknown = client.get("/jobs/j1"), client.get("/jobs/nope")
    assert foreign.status_code == unknown.status_code == 404
    assert foreign.json() == unknown.json()


def test_unknown_job_returns_404(client):
    assert client.get("/jobs/nope").status_code == 404


def test_requires_auth(app):
    with TestClient(app, raise_server_exceptions=False) as c:
        assert c.get("/jobs/j1").status_code == 401


def test_read_failure_returns_503(client, store):
    with patch.object(store, "get", side_effect=OperationalError("s", {}, Exception("x"))):
        assert client.get("/jobs/j1").status_code == 503
