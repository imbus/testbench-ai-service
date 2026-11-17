"""The agent package flow end to end: upload, register, restart, trigger, delete.

Each "restart" is ``loaded.reset()`` (a fresh process has nothing on ``sys.path``)
followed by ``create_app(load_config_from_file(path))``, the same path as the CLI.
TestBench is mocked like in the other integration tests: the session token
dependency and the connection are overridden, the project name lookup is patched.
"""

from __future__ import annotations

import shutil
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, status
from fastapi.testclient import TestClient

from testbench_ai_service.agent_packages import loaded
from testbench_ai_service.auth import AuthInfo, AuthType, validate_auth_token
from testbench_ai_service.config import PROMPTS_DIR, TEMPLATES_DIR
from testbench_ai_service.dependencies import get_tb_connection
from testbench_ai_service.main import create_app
from testbench_ai_service.utils.config import load_config_from_file
from tests.helpers.wheels import RUNNABLE_AGENT_FILES, VALID_ENTRY_POINTS, build_wheel
from tests.integration.conftest import PROJECT_KEY, PROJECT_NAME, TB_SERVER_URL, TOV_KEY, USER_KEY

PACKAGES_URL = "/admin/api/agent-packages"
PACKAGE = "acme-tb-agents"
AGENT_KEY = "renamed_rater"
MARKER = "renamed-rater-template-7f3c"


class Env:
    """A config file with its own prompt, template and package directories."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.prompts = root / "prompts"
        self.templates = root / "templates"
        self.packages = root / "packages"
        self.config_path = root / "config.toml"
        shutil.copytree(PROMPTS_DIR, self.prompts)
        shutil.copytree(TEMPLATES_DIR, self.templates)
        self.config_path.write_text(
            "[testbench-ai-service]\n"
            f'tb_server_url = "{TB_SERVER_URL}"\n'
            f'prompts_dir = "{self.prompts.as_posix()}"\n'
            f'templates_dir = "{self.templates.as_posix()}"\n'
            "\n"
            "[testbench-ai-service.agent_packages]\n"
            "allow_upload = true\n"
            f'dir = "{self.packages.as_posix()}"\n',
            encoding="utf-8",
        )


@pytest.fixture
def env(tmp_path) -> Env:
    return Env(tmp_path)


@contextmanager
def started(env: Env) -> Iterator[tuple[FastAPI, TestClient]]:
    """Start the service from ``env``'s config file as a fresh process would."""
    loaded.reset()
    with (
        patch("testbench_ai_service.config.validate_tb_server_url"),
        patch("testbench_ai_service.main.LLMFactory") as factory_cls,
    ):
        factory = MagicMock()
        factory.close_clients = AsyncMock()
        factory_cls.return_value = factory
        app = create_app(load_config_from_file(str(env.config_path)))
        with TestClient(app, raise_server_exceptions=False) as client:
            yield app, client


def admin_login(client: TestClient) -> dict[str, str]:
    """Sign in to the console as an admin; return the CSRF header for writes."""
    conn = MagicMock()
    conn.session_token = "tb-token-abc"
    conn.read_user_roles.return_value = ["Administrator"]
    conn.get_all_projects.return_value = {"projects": []}
    conn.session.get.return_value.json.return_value = {"key": "u-1"}
    with patch("testbench_ai_service.webui.auth.TBConnection", return_value=conn):
        response = client.post(
            "/admin/api/session", json={"username": "a.mueller", "password": "pw"}
        )
    assert response.status_code == 200, response.text
    return {"X-CSRF-Token": client.cookies["tbai_admin_csrf"]}


def mock_testbench(app: FastAPI) -> None:
    """Authenticate agent requests with a session token against a mocked TestBench."""
    app.dependency_overrides[validate_auth_token] = lambda: AuthInfo(
        auth_type=AuthType.SESSION_TOKEN,
        token="test-session-token",
        user_key=USER_KEY,
        conn=MagicMock(),
    )
    app.dependency_overrides[get_tb_connection] = lambda: MagicMock(server_url=TB_SERVER_URL)


def trigger(client: TestClient):
    with patch("testbench_ai_service.utils.agent.get_project_name", return_value=PROJECT_NAME):
        return client.post(
            f"/agents/{AGENT_KEY}/trigger",
            json={
                "project_key": PROJECT_KEY,
                "tov_key": TOV_KEY,
                "root_uid": "iTB-TC-66",
                "language": "en",
            },
        )


def wait_for_job(client: TestClient, job_id: str) -> Any:
    deadline = time.monotonic() + 10
    while True:
        job = client.get(f"/jobs/{job_id}").json()
        if job["status"] != "running" or time.monotonic() > deadline:
            return job
        time.sleep(0.05)


def upload_and_register(env: Env) -> None:
    """Upload the package and configure its agent as ``renamed_rater``."""
    src = env.root / "src"
    src.mkdir()
    wheel = build_wheel(
        src, name=PACKAGE, files=RUNNABLE_AGENT_FILES, entry_points=VALID_ENTRY_POINTS
    )
    with started(env) as (_app, client):
        headers = admin_login(client)
        with wheel.open("rb") as fh:
            response = client.post(PACKAGES_URL, files={"file": (wheel.name, fh)}, headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["report"]["ok"] is True, response.json()

        response = client.post(
            f"{PACKAGES_URL}/{PACKAGE}/1.0.0/register",
            json={
                "agents": [
                    {
                        "entry_point": "acme_rater",
                        "agent_key": AGENT_KEY,
                        "endpoint_path": "/renamed-rater",
                        "enabled": True,
                    }
                ],
                "overwrite": [],
            },
            headers=headers,
        )
        assert response.status_code == 200, response.text
        assert "agent_packages" in response.json()["restart_required"]

        # Before the restart the package is known but not loaded.
        listing = client.get(PACKAGES_URL).json()
        assert PACKAGE in str(listing)


def test_uploaded_agent_runs_with_its_copied_template_after_a_restart(env):
    upload_and_register(env)
    copied = env.templates / "en" / AGENT_KEY / "template.jinja"
    assert copied.is_file()
    # A marker only the copy carries: the agent must read templates_dir, not the package.
    copied.write_text(f"<p>{MARKER} {{{{ result }}}}</p>", encoding="utf-8")

    with started(env) as (app, client):
        assert loaded.is_loaded(PACKAGE)
        mock_testbench(app)

        response = trigger(client)
        assert response.status_code == status.HTTP_202_ACCEPTED, response.text

        job = wait_for_job(client, response.json()["job_id"])
        assert job["status"] == "succeeded", job
        assert job["agent_key"] == AGENT_KEY
        assert job["report_type"] == "rater"
        assert job["report"]["html"] == f"<p>{MARKER} rated</p>"
        assert Path(job["report"]["template"]) == copied

        # The endpoint path chosen at registration is served as well.
        with patch("testbench_ai_service.utils.agent.get_project_name", return_value=PROJECT_NAME):
            response = client.post(
                "/renamed-rater", json={"project_key": PROJECT_KEY, "tov_key": TOV_KEY}
            )
        assert response.status_code == status.HTTP_202_ACCEPTED, response.text


def test_service_starts_without_the_deleted_package_directory(env):
    upload_and_register(env)
    shutil.rmtree(env.packages)

    with started(env) as (app, client):
        assert not loaded.is_loaded(PACKAGE)
        mock_testbench(app)

        # The agent's own endpoint gets no route.
        with patch("testbench_ai_service.utils.agent.get_project_name", return_value=PROJECT_NAME):
            response = client.post(
                "/renamed-rater", json={"project_key": PROJECT_KEY, "tov_key": TOV_KEY}
            )
        assert response.status_code == status.HTTP_404_NOT_FOUND
        # The generic trigger knows the agent from the config but never imports package
        # code the service did not load at startup (agents/routes._load_package_agent).
        response = trigger(client)
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert f"'{PACKAGE}' is not loaded" in response.json()["detail"]

        admin_login(client)
        with patch("testbench_ai_service.webui.status.requests.get"):
            response = client.get("/admin/api/status")
        assert response.status_code == 200, response.text
        assert "missing" in response.json()["agents"]["unloaded_packages"][PACKAGE]
