from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from testbench_ai_service.agent_packages import loaded
from testbench_ai_service.agent_packages.manifest import load_manifest
from testbench_ai_service.models.config import AgentPackagesConfig
from testbench_ai_service.webui.config_io import read_config_file
from tests.helpers.packages import PACKAGE, install_package
from tests.helpers.wheels import VALID_AGENT_FILES, VALID_ENTRY_POINTS, build_wheel

URL = "/admin/api/agent-packages"
TB_URL = "https://localhost:9443/api/"


@pytest.fixture(autouse=True)
def _reset_loaded():
    yield
    loaded.reset()


class Env:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.prompts = root / "prompts"
        self.templates = root / "templates"
        self.packages = root / "packages"
        self.config_path = root / "config.toml"
        self.prompts.mkdir()
        self.templates.mkdir()
        self.config_path.write_text(
            "[testbench-ai-service]\n"
            f'tb_server_url = "{TB_URL}"\n'
            f'prompts_dir = "{self.prompts.as_posix()}"\n'
            f'templates_dir = "{self.templates.as_posix()}"\n'
            "\n"
            "[testbench-ai-service.agent_packages]\n"
            "allow_upload = true\n"
            f'dir = "{self.packages.as_posix()}"\n',
            encoding="utf-8",
        )

    def kwargs(self, **overrides):

        values = {
            "prompts_dir": self.prompts,
            "templates_dir": self.templates,
            "agent_packages": AgentPackagesConfig(allow_upload=True, dir=self.packages),
            "loaded_from": self.config_path,
        }
        values.update(overrides)
        return {key: value for key, value in values.items() if value is not None}


@pytest.fixture
def env(tmp_path) -> Env:
    return Env(tmp_path)


@pytest.fixture
def pkg_client(make_app, env):
    with TestClient(make_app(**env.kwargs()), raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def admin(pkg_client, tb_connection):
    def _login(roles=None):
        if roles is not None:
            tb_connection.read_user_roles.return_value = roles
        with patch("testbench_ai_service.webui.auth.TBConnection", return_value=tb_connection):
            response = pkg_client.post(
                "/admin/api/session", json={"username": "a.mueller", "password": "pw"}
            )
        assert response.status_code == 200
        return {"X-CSRF-Token": pkg_client.cookies["tbai_admin_csrf"]}

    return _login


def _wheel(tmp_path: Path) -> Path:
    src = tmp_path / "src"
    src.mkdir(exist_ok=True)
    return build_wheel(
        src, version="1.0.0", files=VALID_AGENT_FILES, entry_points=VALID_ENTRY_POINTS
    )


def _upload(client, wheel: Path, headers):
    with wheel.open("rb") as fh:
        return client.post(URL, files={"file": (wheel.name, fh)}, headers=headers)


REGISTER = {
    "agents": [{"entry_point": "acme_rater", "agent_key": "rater2", "endpoint_path": "/rater2"}],
    "overwrite": [],
}


def test_write_routes_need_admin(pkg_client, admin):
    headers = admin(roles=["Tester"])
    assert pkg_client.delete(f"{URL}/{PACKAGE}", headers=headers).status_code == 403
    assert (
        pkg_client.post(f"{URL}/{PACKAGE}/1.0.0/activate", json={}, headers=headers).status_code
        == 403
    )


def test_write_routes_need_csrf(pkg_client, admin):
    admin()
    assert pkg_client.delete(f"{URL}/{PACKAGE}").status_code == 403
    assert pkg_client.post(f"{URL}/{PACKAGE}/1.0.0/register", json=REGISTER).status_code == 403


def test_list_needs_a_session(pkg_client):
    assert pkg_client.get(URL).status_code == 401


def test_upload_is_refused_when_disabled(make_app, env, tb_connection):

    app = make_app(**env.kwargs(agent_packages=AgentPackagesConfig(dir=env.packages)))
    with TestClient(app, raise_server_exceptions=False) as client:
        with patch("testbench_ai_service.webui.auth.TBConnection", return_value=tb_connection):
            client.post("/admin/api/session", json={"username": "a", "password": "p"})
        headers = {"X-CSRF-Token": client.cookies["tbai_admin_csrf"]}
        response = client.post(URL, files={"file": ("x.whl", b"x")}, headers=headers)
        assert response.status_code == 403
        assert client.get(URL).json()["allow_upload"] is False


def test_upload_lists_and_logs(pkg_client, admin, tmp_path, capture):
    headers = admin()
    response = _upload(pkg_client, _wheel(tmp_path), headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["report"]["ok"] is True
    assert body["uploaded_by"] == "a.mueller"
    listing = pkg_client.get(URL).json()
    assert listing["allow_upload"] is True
    assert listing["default_dirs"] is False
    assert [p["name"] for p in listing["packages"]] == [PACKAGE]
    assert listing["packages"][0]["versions"][0]["sha256"] == body["sha256"]
    assert any(body["sha256"] in r.getMessage() for r in capture.records)


def test_upload_of_a_non_wheel_is_422(pkg_client, admin):
    headers = admin()
    response = pkg_client.post(URL, files={"file": ("x.txt", b"x")}, headers=headers)
    assert response.status_code == 422


def test_upload_too_large_is_413(make_app, env, tb_connection, tmp_path):
    app = make_app(**env.kwargs())
    app.state.config.agent_packages.max_upload_mb = 1
    wheel = tmp_path / "big-1.0.0-py3-none-any.whl"
    wheel.write_bytes(b"0" * (1024 * 1024 + 1))
    with TestClient(app, raise_server_exceptions=False) as client:
        with patch("testbench_ai_service.webui.auth.TBConnection", return_value=tb_connection):
            client.post("/admin/api/session", json={"username": "a", "password": "p"})
        headers = {"X-CSRF-Token": client.cookies["tbai_admin_csrf"]}
        assert _upload(client, wheel, headers).status_code == 413


def test_upload_of_changed_content_is_409(pkg_client, admin, env):
    headers = admin()
    install_package(env.packages, active=False, sha256="0" * 64)
    response = _upload(pkg_client, _wheel(env.root), headers)
    assert response.status_code == 409


def test_register_with_default_dirs_is_409(make_app, env, tb_connection):
    app = make_app(**env.kwargs(prompts_dir=None, templates_dir=None))
    install_package(env.packages, active=False)
    with TestClient(app, raise_server_exceptions=False) as client:
        with patch("testbench_ai_service.webui.auth.TBConnection", return_value=tb_connection):
            client.post("/admin/api/session", json={"username": "a", "password": "p"})
        headers = {"X-CSRF-Token": client.cookies["tbai_admin_csrf"]}
        assert client.get(URL).json()["default_dirs"] is True
        response = client.post(f"{URL}/{PACKAGE}/1.0.0/register", json=REGISTER, headers=headers)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "default_dirs"


def test_register_conflict_then_overwrite(pkg_client, admin, env):
    headers = admin()
    install_package(env.packages, active=False)
    existing = env.prompts / "en" / "rater2" / "prompt.yaml"
    existing.parent.mkdir(parents=True)
    existing.write_text("mine", encoding="utf-8")

    response = pkg_client.post(f"{URL}/{PACKAGE}/1.0.0/register", json=REGISTER, headers=headers)
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "file_conflicts"
    assert detail["conflicts"][0]["path"] == "prompts/en/rater2/prompt.yaml"
    assert existing.read_text(encoding="utf-8") == "mine"

    body = {**REGISTER, "overwrite": ["prompts/en/rater2/prompt.yaml"]}
    response = pkg_client.post(f"{URL}/{PACKAGE}/1.0.0/register", json=body, headers=headers)
    assert response.status_code == 200, response.text
    assert "agent_packages" in response.json()["restart_required"]
    assert existing.read_text(encoding="utf-8") != "mine"

    package = pkg_client.get(URL).json()["packages"][0]
    assert package["registered"] == {"rater2": "acme_rater"}


def test_remove_deletes_the_agents_from_the_config(pkg_client, admin, env):
    headers = admin()
    install_package(env.packages, active=False)
    registered = pkg_client.post(f"{URL}/{PACKAGE}/1.0.0/register", json=REGISTER, headers=headers)
    assert registered.status_code == 200, registered.text
    assert "rater2" in read_config_file(env.config_path)["agents"]

    response = pkg_client.delete(f"{URL}/{PACKAGE}", headers=headers)

    assert response.status_code == 200, response.text
    assert "rater2" not in read_config_file(env.config_path).get("agents", {})
    assert load_manifest(env.packages).active(PACKAGE) is None


def test_remove_unknown_package_is_404(pkg_client, admin):
    headers = admin()
    assert pkg_client.delete(f"{URL}/nope", headers=headers).status_code == 404


def test_activate_unknown_version_is_404(pkg_client, admin):
    headers = admin()
    response = pkg_client.post(f"{URL}/{PACKAGE}/9.9.9/activate", json={}, headers=headers)
    assert response.status_code == 404


def test_delete_version(pkg_client, admin, env):
    headers = admin()
    install_package(env.packages, active=True)
    assert pkg_client.delete(f"{URL}/{PACKAGE}/1.0.0", headers=headers).status_code == 409
    install_package(env.packages, version="2.0.0", active=False)
    assert pkg_client.delete(f"{URL}/{PACKAGE}/2.0.0", headers=headers).status_code == 204
    assert "2.0.0" not in load_manifest(env.packages).packages[PACKAGE]


@pytest.mark.parametrize("name", ["%2E%2E", "..%2F..", "a%2F..", "bad..name"])
def test_unsafe_names_are_rejected(pkg_client, admin, name):
    headers = admin()
    response = pkg_client.delete(f"{URL}/{name}/1.0.0", headers=headers)
    assert response.status_code in (400, 404, 405)
    response = pkg_client.delete(f"{URL}/{name}", headers=headers)
    assert response.status_code in (400, 404, 405)


def test_unsafe_name_in_a_matching_route_is_400(pkg_client, admin):
    headers = admin()
    assert pkg_client.delete(f"{URL}/..x/1.0.0", headers=headers).status_code == 400
