from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from testbench_ai_service.webui.config_io import REDACTED_SENTINEL
from testbench_ai_service.webui.routes import _plan_change

COMMENTED = """\
[testbench-ai-service]
# Which TestBench we talk to.
tb_server_url = "https://localhost:9443/api/"
port = 8010
"""

# A real-looking provider credential, an adjacent non-secret key right next to
# it (so a diff's context lines would include the secret if it were not
# redacted), a legitimate enum value that merely contains the substring
# "api_key", and a certificate path that merely contains the bare substring
# "key" -- the last two must NOT be redacted.
CREDENTIALED = """\
[testbench-ai-service]
port = 8010

[testbench-ai-service.llm_config]
# Provider credential -- must never leave this file.
api_key = "sk-REAL-SECRET-VALUE"
model = "gpt-4"
auth_method = "api_key"
ssl_key = "/etc/certs/key.pem"
"""


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(COMMENTED, encoding="utf-8")
    return path


@pytest.fixture
def app_with_file(make_app, config_file: Path):
    app = make_app()
    app.state.config_path = config_file
    return app


@pytest.fixture
def file_client(app_with_file):
    with TestClient(app_with_file, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def admin(file_client, tb_connection):
    def _login(roles=None):
        if roles is not None:
            tb_connection.read_user_roles.return_value = roles
        with patch("testbench_ai_service.webui.auth.TBConnection", return_value=tb_connection):
            return file_client.post(
                "/admin/api/session", json={"username": "a.mueller", "password": "pw"}
            )

    return _login


@pytest.fixture
def credentialed_config_file(tmp_path: Path) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(CREDENTIALED, encoding="utf-8")
    return path


@pytest.fixture
def credentialed_app(make_app, credentialed_config_file: Path):
    app = make_app()
    app.state.config_path = credentialed_config_file
    return app


@pytest.fixture
def credentialed_client(credentialed_app):
    with TestClient(credentialed_app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def credentialed_admin(credentialed_client, tb_connection):
    def _login(roles=None):
        if roles is not None:
            tb_connection.read_user_roles.return_value = roles
        with patch("testbench_ai_service.webui.auth.TBConnection", return_value=tb_connection):
            return credentialed_client.post(
                "/admin/api/session", json={"username": "a.mueller", "password": "pw"}
            )

    return _login


def csrf(client) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies["tbai_admin_csrf"]}


def test_preview_of_no_edits_reports_no_diff(file_client, admin):
    admin()

    body = file_client.post(
        "/admin/api/config/preview", json={"edits": {}}, headers=csrf(file_client)
    ).json()

    assert body["valid"] is True
    assert body["issues"] == []
    assert body["diffs"] == []
    assert body["restart_required"] == []


def test_preview_returns_the_rendered_toml_even_with_no_edits(file_client, admin):
    admin()

    body = file_client.post(
        "/admin/api/config/preview", json={"edits": {}}, headers=csrf(file_client)
    ).json()

    assert body["toml"] == COMMENTED


def test_preview_of_a_scalar_edit_diffs_that_line_only(file_client, admin):
    admin()

    body = file_client.post(
        "/admin/api/config/preview",
        json={"edits": {"port": 9999}},
        headers=csrf(file_client),
    ).json()

    assert body["valid"] is True
    assert len(body["diffs"]) == 1
    assert body["diffs"][0]["added"] == 1
    assert body["diffs"][0]["removed"] == 1
    assert "+port = 9999" in body["diffs"][0]["diff"]
    assert "# Which TestBench we talk to." in body["toml"]


def test_preview_names_the_config_path_in_the_diff(file_client, admin, config_file):
    admin()

    body = file_client.post(
        "/admin/api/config/preview",
        json={"edits": {"port": 9999}},
        headers=csrf(file_client),
    ).json()

    assert body["diffs"][0]["path"] == str(config_file.resolve())


def test_preview_reports_a_restart_requiring_edit(file_client, admin):
    admin()

    body = file_client.post(
        "/admin/api/config/preview",
        json={"edits": {"port": 9999}},
        headers=csrf(file_client),
    ).json()

    assert body["restart_required"] == ["port"]


def test_preview_reports_a_hot_swappable_edit_as_needing_no_restart(file_client, admin):
    admin()

    body = file_client.post(
        "/admin/api/config/preview",
        json={"edits": {"language": "en"}},
        headers=csrf(file_client),
    ).json()

    assert body["restart_required"] == []


def test_preview_of_an_invalid_edit_reports_issues_and_no_diff(file_client, admin):
    admin()

    body = file_client.post(
        "/admin/api/config/preview",
        json={"edits": {"port": "not a number"}},
        headers=csrf(file_client),
    ).json()

    assert body["valid"] is False
    assert [issue["path"] for issue in body["issues"]] == ["port"]
    # No diff: there is nothing to approve, because nothing could be written.
    assert body["diffs"] == []


def test_preview_writes_nothing(file_client, admin, config_file):
    admin()
    before = config_file.read_text(encoding="utf-8")

    file_client.post(
        "/admin/api/config/preview",
        json={"edits": {"port": 9999}},
        headers=csrf(file_client),
    )

    assert config_file.read_text(encoding="utf-8") == before
    assert not config_file.with_name("config.toml.bak").exists()


def test_preview_refuses_the_redaction_sentinel(file_client, admin):
    admin()

    response = file_client.post(
        "/admin/api/config/preview",
        json={"edits": {"llm_config.api_key": REDACTED_SENTINEL}},
        headers=csrf(file_client),
    )

    assert response.status_code == 400


def test_preview_refuses_a_non_admin(file_client, admin):
    admin(roles=["Test Manager"])

    response = file_client.post(
        "/admin/api/config/preview", json={"edits": {}}, headers=csrf(file_client)
    )

    assert response.status_code == 403


def test_preview_refuses_a_missing_csrf_header(file_client, admin):
    admin()

    response = file_client.post("/admin/api/config/preview", json={"edits": {}})

    assert response.status_code == 403


def test_preview_refuses_an_anonymous_caller(file_client):
    response = file_client.post("/admin/api/config/preview", json={"edits": {}})

    assert response.status_code == 401


def test_preview_reports_in_flight_tasks(file_client, admin, app_with_file):
    admin()
    app_with_file.state.task_registry._labels.append("test_case_set_reviewer")
    try:
        body = file_client.post(
            "/admin/api/config/preview", json={"edits": {}}, headers=csrf(file_client)
        ).json()
    finally:
        app_with_file.state.task_registry._labels.clear()

    assert body["in_flight_tasks"] == 1


def test_preview_redacts_a_credential_from_the_toml_even_with_no_edits(
    credentialed_client, credentialed_admin
):
    credentialed_admin()

    body = credentialed_client.post(
        "/admin/api/config/preview",
        json={"edits": {}},
        headers=csrf(credentialed_client),
    ).json()

    assert "sk-REAL-SECRET-VALUE" not in body["toml"]
    assert REDACTED_SENTINEL in body["toml"]


def test_preview_of_an_adjacent_edit_does_not_leak_the_secret_into_the_diff(
    credentialed_client, credentialed_admin
):
    credentialed_admin()

    body = credentialed_client.post(
        "/admin/api/config/preview",
        json={"edits": {"llm_config.model": "gpt-4o"}},
        headers=csrf(credentialed_client),
    ).json()

    assert "sk-REAL-SECRET-VALUE" not in body["diffs"][0]["diff"]
    assert REDACTED_SENTINEL in body["diffs"][0]["diff"]


def test_plan_change_still_writes_the_real_secret(credentialed_config_file, make_app):
    """The tuple's second element is what ``apply`` (Task 12) writes to disk.

    It must stay the RAW rendered text, never the redacted display text --
    otherwise applying an unrelated edit would overwrite the operator's real
    credential with the literal sentinel string. This is the guard against
    "fixing" the leak by redacting the write path instead of only the
    response.
    """
    app = make_app()
    running = app.state.config

    _preview, text_to_write = _plan_change(
        {"llm_config.model": "gpt-4o"}, credentialed_config_file, running
    )

    assert "sk-REAL-SECRET-VALUE" in text_to_write
    assert REDACTED_SENTINEL not in text_to_write


def test_preview_does_not_redact_a_legitimate_enum_value_containing_api_key(
    credentialed_client, credentialed_admin
):
    credentialed_admin()

    body = credentialed_client.post(
        "/admin/api/config/preview",
        json={"edits": {}},
        headers=csrf(credentialed_client),
    ).json()

    assert 'auth_method = "api_key"' in body["toml"]


def test_preview_does_not_redact_a_certificate_path_with_bare_key_substring(
    credentialed_client, credentialed_admin
):
    credentialed_admin()

    body = credentialed_client.post(
        "/admin/api/config/preview",
        json={"edits": {}},
        headers=csrf(credentialed_client),
    ).json()

    assert 'ssl_key = "/etc/certs/key.pem"' in body["toml"]


def test_preview_redaction_preserves_comments(credentialed_client, credentialed_admin):
    credentialed_admin()

    body = credentialed_client.post(
        "/admin/api/config/preview",
        json={"edits": {}},
        headers=csrf(credentialed_client),
    ).json()

    assert "# Provider credential -- must never leave this file." in body["toml"]
