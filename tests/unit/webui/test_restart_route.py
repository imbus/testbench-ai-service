"""POST /admin/api/restart -- the console's in-process restart."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from testbench_ai_service.restart import RestartController

CONFIG = """\
[testbench-ai-service]
tb_server_url = "https://localhost:9443/api/"
port = 8020
"""


@pytest.fixture
def controller() -> MagicMock:
    controller = MagicMock(spec=RestartController)
    controller.apply_overrides = MagicMock()
    return controller


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(CONFIG, encoding="utf-8")
    return path


@pytest.fixture
def restart_app(make_app, config_file, controller):
    app = make_app()
    app.state.config_path = config_file
    app.state.restart_controller = controller
    return app


@pytest.fixture
def restart_client(restart_app):
    with TestClient(restart_app, raise_server_exceptions=False) as c:
        yield c


def _sign_in(client, tb_connection, roles=("Administrator",)):
    tb_connection.read_user_roles.return_value = list(roles)
    with patch("testbench_ai_service.webui.auth.TBConnection", return_value=tb_connection):
        response = client.post(
            "/admin/api/session", json={"username": "a.mueller", "password": "pw"}
        )
    assert response.status_code == 200


def _restart(client):
    return client.post(
        "/admin/api/restart", headers={"X-CSRF-Token": client.cookies["tbai_admin_csrf"]}
    )


@pytest.fixture
def run_soon():
    """Run the deferred ``controller.request`` right away instead of after the response."""
    with patch("testbench_ai_service.webui.routes.RESTART_DELAY_SECONDS", 0):
        yield


def test_restart_asks_the_serving_loop_and_names_the_new_address(
    restart_client, tb_connection, controller, run_soon
):
    _sign_in(restart_client, tb_connection)

    response = _restart(restart_client)

    assert response.status_code == 202
    body = response.json()
    assert body["port"] == 8020
    assert body["tls"] is False
    controller.apply_overrides.assert_called_once()
    # The request is deferred to after the response; the next request lets it run.
    restart_client.get("/admin/api/session")
    controller.request.assert_called_once()


def test_restart_requires_an_administrator(restart_client, tb_connection, controller):
    _sign_in(restart_client, tb_connection, roles=("Tester",))

    response = _restart(restart_client)

    assert response.status_code == 403
    controller.request.assert_not_called()


def test_restart_requires_the_csrf_header(restart_client, tb_connection, controller):
    _sign_in(restart_client, tb_connection)

    response = restart_client.post("/admin/api/restart")

    assert response.status_code == 403
    controller.request.assert_not_called()


def test_restart_refuses_a_config_the_service_could_not_start_with(
    restart_client, tb_connection, controller, config_file
):
    _sign_in(restart_client, tb_connection)
    config_file.write_text(
        '[testbench-ai-service]\ntb_server_url = "https://localhost:9443/api/"\nport = "x"\n',
        encoding="utf-8",
    )

    response = _restart(restart_client)

    assert response.status_code == 422
    assert response.json()["detail"]["issues"]
    controller.request.assert_not_called()


def test_restart_is_unavailable_without_the_serving_loop(make_app, tb_connection):
    with TestClient(make_app(), raise_server_exceptions=False) as client:
        _sign_in(client, tb_connection)

        response = _restart(client)

    assert response.status_code == 409


def test_status_says_whether_a_restart_is_possible(restart_client, tb_connection, make_app):
    _sign_in(restart_client, tb_connection)
    service = restart_client.get("/admin/api/status").json()["service"]
    assert service["can_restart"] is True
    assert service["started_at"]

    with TestClient(make_app(), raise_server_exceptions=False) as client:
        _sign_in(client, tb_connection)
        assert client.get("/admin/api/status").json()["service"]["can_restart"] is False
