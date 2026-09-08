from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from testbench_ai_service.config import AppConfig
from testbench_ai_service.main import create_app
from testbench_ai_service.models.webui import AdminUiConfig

TB_URL = "https://localhost:9443/api/"


def _app(**config_kwargs):
    with (
        patch("testbench_ai_service.config.validate_tb_server_url"),
        patch("testbench_ai_service.main.LLMFactory") as factory_cls,
    ):
        instance = MagicMock()
        instance.init_clients = MagicMock()
        instance.close_clients = AsyncMock()
        factory_cls.return_value = instance
        return create_app(AppConfig(tb_server_url=TB_URL, **config_kwargs))


def test_admin_ui_enabled_by_default():
    assert AdminUiConfig().enabled is True
    assert AdminUiConfig().require_loopback is False


def test_console_routes_present_when_enabled():
    app = _app()
    # FastAPI's newer `include_router` wraps included routers as internal
    # `_IncludedRouter` objects with no `.path` attribute, so routes added via
    # `app.mount()` (the SPA static mount) are the reliable way to check
    # `app.routes` directly here.
    paths = {getattr(route, "path", None) for route in app.routes}
    assert any(path is not None and path.startswith("/admin") for path in paths)


def test_console_absent_when_disabled():
    app = _app(admin_ui=AdminUiConfig(enabled=False))
    paths = {getattr(route, "path", None) for route in app.routes}
    assert not any(path is not None and path.startswith("/admin") for path in paths)
    # The agent API is unaffected.
    assert "/agents" in app.openapi()["paths"]


def test_existing_root_redirect_still_works():
    app = _app()
    with TestClient(app) as client:
        response = client.get("/", follow_redirects=False)
        assert response.status_code in (307, 302)
        assert response.headers["location"] == "/docs"


def test_warns_when_enabled_on_non_loopback_bind(caplog):
    with caplog.at_level("WARNING"):
        _app(host="0.0.0.0")  # noqa: S104 - deliberately testing this case
    assert any("reachable" in record.message.lower() for record in caplog.records)


def test_no_warning_on_loopback_bind(caplog):
    with caplog.at_level("WARNING"):
        _app(host="127.0.0.1")
    assert not any("reachable" in record.message.lower() for record in caplog.records)


def test_warns_on_empty_host_bind(caplog):
    """An empty host conventionally means INADDR_ANY (bind on all interfaces),
    the opposite of loopback, so it must still warn."""
    with caplog.at_level("WARNING"):
        _app(host="")
    assert any("reachable" in record.message.lower() for record in caplog.records)


def test_app_records_start_time_and_config_path():
    app = _app()
    assert app.state.started_at is not None
    assert app.state.config_path is not None
