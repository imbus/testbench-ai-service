from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from testbench_ai_service.agent_packages import loaded
from testbench_ai_service.agent_packages.manifest import load_manifest
from testbench_ai_service.models.config import AgentPackagesConfig
from testbench_ai_service.webui.config_io import read_config_file
from tests.helpers.packages import PACKAGE, install_package, llm_report
from tests.helpers.wheels import (
    VALID_AGENT_FILES,
    VALID_ENTRY_POINTS,
    VALID_LLM_CLIENT_FILES,
    VALID_LLM_ENTRY_POINTS,
    build_wheel,
)

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


def test_register_keeps_files_listed_in_keep(pkg_client, admin, env):
    headers = admin()
    install_package(env.packages, active=False)
    prompt = env.prompts / "en" / "rater2" / "prompt.yaml"
    started = env.templates / "en" / "rater2" / "started.jinja"
    for path in (prompt, started):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("mine", encoding="utf-8")
    register = f"{URL}/{PACKAGE}/1.0.0/register"

    # One file decided, the other not: still a conflict, naming the undecided one.
    body = {**REGISTER, "keep": ["prompts/en/rater2/prompt.yaml"]}
    response = pkg_client.post(register, json=body, headers=headers)
    assert response.status_code == 409
    paths = [c["path"] for c in response.json()["detail"]["conflicts"]]
    assert paths == ["templates/en/rater2/started.jinja"]

    body["overwrite"] = ["templates/en/rater2/started.jinja"]
    response = pkg_client.post(register, json=body, headers=headers)
    assert response.status_code == 200, response.text
    assert prompt.read_text(encoding="utf-8") == "mine"
    assert started.read_text(encoding="utf-8") != "mine"


def test_register_with_a_file_both_kept_and_overwritten_is_422(pkg_client, admin, env):
    headers = admin()
    install_package(env.packages, active=False)
    label = "prompts/en/rater2/prompt.yaml"
    body = {**REGISTER, "keep": [label], "overwrite": [label]}

    response = pkg_client.post(f"{URL}/{PACKAGE}/1.0.0/register", json=body, headers=headers)

    assert response.status_code == 422
    assert label in response.json()["detail"]["message"]


def test_activate_accepts_keep(pkg_client, admin, env):
    headers = admin()
    install_package(env.packages, version="1.0.0", active=False)
    registered = pkg_client.post(f"{URL}/{PACKAGE}/1.0.0/register", json=REGISTER, headers=headers)
    assert registered.status_code == 200, registered.text
    system = env.prompts / "en" / "rater2" / "system.jinja"
    system.write_text("edited", encoding="utf-8")
    install_package(env.packages, version="2.0.0", active=False)
    activate = f"{URL}/{PACKAGE}/2.0.0/activate"

    assert pkg_client.post(activate, json={}, headers=headers).status_code == 409
    body = {"keep": ["prompts/en/rater2/system.jinja"]}
    response = pkg_client.post(activate, json=body, headers=headers)

    assert response.status_code == 200, response.text
    assert system.read_text(encoding="utf-8") == "edited"


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


@pytest.mark.parametrize("name", ["%2E%2E", "bad..name", "..x", ".hidden"])
def test_unsafe_names_are_rejected_with_400(pkg_client, admin, name):
    headers = admin()
    assert pkg_client.delete(f"{URL}/{name}", headers=headers).status_code == 400
    assert pkg_client.delete(f"{URL}/{name}/1.0.0", headers=headers).status_code == 400
    assert pkg_client.delete(f"{URL}/{PACKAGE}/{name}", headers=headers).status_code == 400


@pytest.mark.parametrize("name", ["..%2F..", "a%2F.."])
def test_encoded_slashes_are_refused(pkg_client, admin, name):
    """Depending on how the router splits the path this is 400 (segment check) or 404/405."""
    headers = admin()
    for url in (f"{URL}/{name}", f"{URL}/{name}/1.0.0"):
        assert pkg_client.delete(url, headers=headers).status_code in (400, 404, 405)


# --- the LLM client of a package -------------------------------------------------------

USE_CLIENT = {"entry_point": "acme_llm", "models": ["acme-large", "acme-small"]}
CLIENT_URL = f"{URL}/{PACKAGE}/1.0.0/llm-client"


def _install_llm(env, version: str = "1.0.0"):
    return install_package(
        env.packages,
        version=version,
        active=False,
        files=VALID_LLM_CLIENT_FILES,
        entry_points={},
        llm_entry_points=VALID_LLM_ENTRY_POINTS,
        reports={},
        llm_clients={"acme_llm": llm_report()},
    )


def test_llm_client_routes_need_admin(pkg_client, admin):
    headers = admin(roles=["Tester"])
    assert pkg_client.post(CLIENT_URL, json=USE_CLIENT, headers=headers).status_code == 403
    assert pkg_client.delete(f"{URL}/{PACKAGE}/llm-client", headers=headers).status_code == 403


def test_llm_client_routes_need_csrf(pkg_client, admin):
    admin()
    assert pkg_client.post(CLIENT_URL, json=USE_CLIENT).status_code == 403
    assert pkg_client.delete(f"{URL}/{PACKAGE}/llm-client").status_code == 403


def test_use_llm_client_writes_the_config_and_lists_it(pkg_client, admin, env):
    headers = admin()
    _install_llm(env)

    response = pkg_client.post(
        CLIENT_URL, json={**USE_CLIENT, "default_model": "acme-large"}, headers=headers
    )

    assert response.status_code == 200, response.text
    assert "agent_packages" in response.json()["restart_required"]
    llm = read_config_file(env.config_path)["llm_config"]
    assert llm["provider"] == "custom"
    assert llm["package"] == PACKAGE
    assert llm["model"] == "acme-large"
    assert set(llm["extra_models"]) == {"acme-large", "acme-small"}
    listed = pkg_client.get(URL).json()["packages"][0]
    assert listed["llm_client"] == "acme_llm"
    assert listed["versions"][0]["report"]["llm_clients"]["acme_llm"]["ok"] is True


def test_a_package_not_in_use_lists_no_llm_client(pkg_client, admin, env):
    admin()
    _install_llm(env)
    assert pkg_client.get(URL).json()["packages"][0]["llm_client"] is None


def test_use_llm_client_with_a_reserved_model_name_is_422(pkg_client, admin, env):
    headers = admin()
    _install_llm(env)
    body = {"entry_point": "acme_llm", "models": ["gpt-acme"]}

    response = pkg_client.post(CLIENT_URL, json=body, headers=headers)

    assert response.status_code == 422
    assert "gpt-acme" in response.json()["detail"]["message"]
    assert "llm_config" not in read_config_file(env.config_path)


def test_use_llm_client_without_models_is_422(pkg_client, admin, env):
    headers = admin()
    _install_llm(env)
    response = pkg_client.post(
        CLIENT_URL, json={"entry_point": "acme_llm", "models": []}, headers=headers
    )
    assert response.status_code == 422


def test_use_llm_client_of_an_unknown_version_is_404(pkg_client, admin):
    headers = admin()
    assert pkg_client.post(CLIENT_URL, json=USE_CLIENT, headers=headers).status_code == 404


def test_clear_llm_client_restores_the_default_provider(pkg_client, admin, env):
    headers = admin()
    _install_llm(env)
    assert pkg_client.post(CLIENT_URL, json=USE_CLIENT, headers=headers).status_code == 200

    response = pkg_client.delete(f"{URL}/{PACKAGE}/llm-client", headers=headers)

    assert response.status_code == 200, response.text
    assert "agent_packages" in response.json()["restart_required"]
    assert "provider" not in read_config_file(env.config_path).get("llm_config", {})
    assert load_manifest(env.packages).active(PACKAGE) is None
    # The version itself is still there: the clear route is not the version delete.
    assert "1.0.0" in load_manifest(env.packages).packages[PACKAGE]


def test_clear_llm_client_of_a_package_not_in_use_is_409(pkg_client, admin, env):
    headers = admin()
    _install_llm(env)
    response = pkg_client.delete(f"{URL}/{PACKAGE}/llm-client", headers=headers)
    assert response.status_code == 409
    assert "1.0.0" in load_manifest(env.packages).packages[PACKAGE]


def test_removing_a_package_in_use_as_llm_client_is_409(pkg_client, admin, env):
    headers = admin()
    _install_llm(env)
    assert pkg_client.post(CLIENT_URL, json=USE_CLIENT, headers=headers).status_code == 200
    assert pkg_client.delete(f"{URL}/{PACKAGE}", headers=headers).status_code == 409


# --- serialisation of console writes ---------------------------------------------------

PROMPT_URL = "/admin/api/prompts/en/some_agent"
LOCKED_WRITES = {
    "apply_config": ("POST", "/admin/api/config/apply", {"edits": {}}),
    "fork_prompt": (
        "POST",
        f"{PROMPT_URL}/fork",
        {"project": "p", "directory": "d"},
    ),
    "save_prompt": ("PUT", PROMPT_URL, {}),
    "package_delete": ("DELETE", f"{URL}/{PACKAGE}", None),
    "package_activate": ("POST", f"{URL}/{PACKAGE}/1.0.0/activate", {}),
    "package_register": ("POST", f"{URL}/{PACKAGE}/1.0.0/register", REGISTER),
    "package_upload": ("POST", URL, None),
    "package_use_llm_client": ("POST", f"{URL}/{PACKAGE}/1.0.0/llm-client", USE_CLIENT),
    "package_clear_llm_client": ("DELETE", f"{URL}/{PACKAGE}/llm-client", None),
}


def _request_in_thread(client, method, url, json, headers):
    result: dict = {}

    def run() -> None:
        kwargs: dict = {"headers": headers}
        if method == "POST" and url == URL:
            kwargs["files"] = {"file": ("x.txt", b"x")}
        elif json is not None:
            kwargs["json"] = json
        result["response"] = client.request(method, url, **kwargs)

    thread = threading.Thread(target=run)
    thread.start()
    return thread, result


@pytest.mark.parametrize("route", sorted(LOCKED_WRITES))
def test_writes_wait_for_the_config_write_lock(pkg_client, admin, route):
    headers = admin()
    method, url, json = LOCKED_WRITES[route]
    lock = pkg_client.app.state.config_write_lock
    pkg_client.portal.call(lock.acquire)
    try:
        thread, result = _request_in_thread(pkg_client, method, url, json, headers)
        thread.join(1.0)
        assert thread.is_alive(), f"{route} finished while the write lock was held"
    finally:
        pkg_client.portal.call(lock.release)
    thread.join(30)
    assert not thread.is_alive()
    assert result["response"].status_code != 500


@pytest.mark.parametrize("route", sorted(LOCKED_WRITES))
def test_rejected_requests_do_not_wait_for_the_lock(pkg_client, admin, route):
    method, url, json = LOCKED_WRITES[route]
    lock = pkg_client.app.state.config_write_lock
    good = admin()
    pkg_client.portal.call(lock.acquire)
    try:
        # Without the CSRF header, then as a non-admin: both are refused at once.
        for headers in ({}, admin(roles=["Tester"])):
            thread, result = _request_in_thread(pkg_client, method, url, json, headers)
            thread.join(10)
            assert not thread.is_alive(), f"{route} waited for the lock before refusing"
            assert result["response"].status_code == 403
    finally:
        pkg_client.portal.call(lock.release)
    assert good  # the admin session itself was valid
