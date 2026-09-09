from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from testbench_ai_service.webui.config_io import REDACTED_SENTINEL, read_config_file
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

# config.toml is a potentially shared file (load_config_from_file falls back
# to pyproject.toml), so a credential planted in another tool's
# [[array.of.tables]] section -- outside [testbench-ai-service] entirely --
# is a realistic shape the rendered `toml` (the WHOLE file, not only the
# service's own table) must still hide.
CREDENTIALED_AOT = """\
[testbench-ai-service]
port = 8010

[[tool.other.entries]]
api_key = "sk-IN-AOT"
name = "one"

[[tool.other.entries]]
api_key = "sk-IN-AOT-2"
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


@pytest.fixture
def aot_config_file(tmp_path: Path) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(CREDENTIALED_AOT, encoding="utf-8")
    return path


@pytest.fixture
def aot_app(make_app, aot_config_file: Path):
    app = make_app()
    app.state.config_path = aot_config_file
    return app


@pytest.fixture
def aot_client(aot_app):
    with TestClient(aot_app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def aot_admin(aot_client, tb_connection):
    def _login(roles=None):
        if roles is not None:
            tb_connection.read_user_roles.return_value = roles
        with patch("testbench_ai_service.webui.auth.TBConnection", return_value=tb_connection):
            return aot_client.post(
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


def test_preview_redacts_a_credential_inside_an_array_of_tables(aot_client, aot_admin):
    """The array-of-tables leak: the rendered `toml` is the WHOLE file, not
    only `[testbench-ai-service]`, so another tool's `[[array.of.tables]]`
    section holding a credential must be redacted too, for every entry."""
    aot_admin()

    body = aot_client.post(
        "/admin/api/config/preview", json={"edits": {}}, headers=csrf(aot_client)
    ).json()

    assert "sk-IN-AOT" not in body["toml"]
    assert "sk-IN-AOT-2" not in body["toml"]
    assert body["toml"].count(REDACTED_SENTINEL) == 2


def test_apply_writes_the_change_and_keeps_the_comments(file_client, admin, config_file):
    admin()

    body = file_client.post(
        "/admin/api/config/apply",
        json={"edits": {"port": 9999}},
        headers=csrf(file_client),
    ).json()

    written = config_file.read_text(encoding="utf-8")
    assert "port = 9999" in written
    assert "# Which TestBench we talk to." in written
    assert body["written"] == [str(config_file.resolve())]


def test_apply_keeps_the_previous_contents_as_a_backup(file_client, admin, config_file):
    admin()

    body = file_client.post(
        "/admin/api/config/apply",
        json={"edits": {"port": 9999}},
        headers=csrf(file_client),
    ).json()

    backup = config_file.with_name("config.toml.bak")
    assert body["backup"] == str(backup)
    assert backup.read_text(encoding="utf-8") == COMMENTED


def test_apply_hot_reloads_a_swappable_change(file_client, admin, app_with_file):
    admin()

    # Correction 3: hot_reload constructs its own LLMFactory inside
    # webui.reload rather than reusing app.state.llm_factory, so the
    # conftest's make_app patch of testbench_ai_service.main.LLMFactory
    # (startup only) does not reach it. With no OPENAI_API_KEY set in this
    # environment and "openai" as the default provider, an unpatched
    # LLMFactory().init_clients() would raise and hot_reload would (correctly)
    # report reloaded=False. Patch the same target test_reload.py already
    # does, so this test exercises a *clean* reload.
    new_factory = MagicMock()
    new_factory.init_clients = MagicMock()
    new_factory.close_clients = AsyncMock()
    with patch("testbench_ai_service.webui.reload.LLMFactory", MagicMock(return_value=new_factory)):
        body = file_client.post(
            "/admin/api/config/apply",
            json={"edits": {"language": "en"}},
            headers=csrf(file_client),
        ).json()

    assert body["reloaded"] is True
    assert body["restart_required"] == []
    assert app_with_file.state.config.language.value == "en"


def test_apply_writes_a_restart_requiring_change_but_does_not_swap_it(
    file_client, admin, app_with_file, config_file
):
    """The file is the source of truth; a port swap the process cannot honour
    must not be reported as live."""
    admin()

    body = file_client.post(
        "/admin/api/config/apply",
        json={"edits": {"port": 9999}},
        headers=csrf(file_client),
    ).json()

    assert body["restart_required"] == ["port"]
    assert "port = 9999" in config_file.read_text(encoding="utf-8")
    assert app_with_file.state.config.port == 8010


def test_apply_of_an_invalid_edit_writes_nothing(file_client, admin, config_file):
    admin()
    before = config_file.read_text(encoding="utf-8")

    response = file_client.post(
        "/admin/api/config/apply",
        json={"edits": {"port": "not a number"}},
        headers=csrf(file_client),
    )

    assert response.status_code == 422
    assert config_file.read_text(encoding="utf-8") == before
    assert not config_file.with_name("config.toml.bak").exists()


def test_apply_of_an_invalid_edit_returns_the_issues(file_client, admin):
    admin()

    body = file_client.post(
        "/admin/api/config/apply",
        json={"edits": {"port": "not a number"}},
        headers=csrf(file_client),
    ).json()

    assert [issue["path"] for issue in body["detail"]["issues"]] == ["port"]


def test_apply_with_no_edits_writes_nothing_and_reports_nothing_written(
    file_client, admin, config_file
):
    admin()

    body = file_client.post(
        "/admin/api/config/apply", json={"edits": {}}, headers=csrf(file_client)
    ).json()

    assert body["written"] == []
    assert body["backup"] is None
    assert not config_file.with_name("config.toml.bak").exists()


def test_apply_refuses_the_redaction_sentinel(file_client, admin, config_file):
    admin()
    before = config_file.read_text(encoding="utf-8")

    response = file_client.post(
        "/admin/api/config/apply",
        json={"edits": {"llm_config.api_key": REDACTED_SENTINEL}},
        headers=csrf(file_client),
    )

    assert response.status_code == 400
    assert config_file.read_text(encoding="utf-8") == before


def test_apply_refuses_a_non_admin(file_client, admin, config_file):
    admin(roles=["Test Manager"])
    before = config_file.read_text(encoding="utf-8")

    response = file_client.post(
        "/admin/api/config/apply",
        json={"edits": {"port": 9999}},
        headers=csrf(file_client),
    )

    assert response.status_code == 403
    assert config_file.read_text(encoding="utf-8") == before


def test_apply_refuses_a_missing_csrf_header(file_client, admin, config_file):
    admin()
    before = config_file.read_text(encoding="utf-8")

    response = file_client.post("/admin/api/config/apply", json={"edits": {"port": 9999}})

    assert response.status_code == 403
    assert config_file.read_text(encoding="utf-8") == before


def test_apply_removing_a_key_falls_back_to_the_default(file_client, admin, config_file):
    admin()

    file_client.post(
        "/admin/api/config/apply",
        json={"edits": {"port": None}},
        headers=csrf(file_client),
    )

    assert "port" not in config_file.read_text(encoding="utf-8")


def test_a_second_apply_sees_the_first_ones_change(file_client, admin, config_file):
    """The overlay merges into disk, so nothing silently reverts."""
    admin()

    file_client.post(
        "/admin/api/config/apply",
        json={"edits": {"language": "en"}},
        headers=csrf(file_client),
    )
    file_client.post(
        "/admin/api/config/apply",
        json={"edits": {"debug": True}},
        headers=csrf(file_client),
    )

    written = config_file.read_text(encoding="utf-8")
    assert 'language = "en"' in written
    assert "debug = true" in written


def test_apply_refuses_an_unwritable_log_path(file_client, admin, config_file):
    """Spec 6.3 regression guard: the console must never write a config.toml
    the service could not boot with. Before FIX A, this edit wrote
    successfully -- AppConfig has no opinion on log-path writability -- and
    left a config that would crash setup_logging()'s RotatingFileHandler at
    the very next startup, with no way back in through the console."""
    admin()
    before = config_file.read_text(encoding="utf-8")
    bad_path = str(config_file.parent / "missing" / "nested" / "svc.log")

    response = file_client.post(
        "/admin/api/config/apply",
        json={"edits": {"logging.file.file_name": bad_path}},
        headers=csrf(file_client),
    )

    assert response.status_code == 422
    assert config_file.read_text(encoding="utf-8") == before
    assert not config_file.with_name("config.toml.bak").exists()


def test_apply_refuses_a_log_path_that_is_an_existing_directory(file_client, admin, config_file):
    """Fix Round 2, Fix 1 regression guard: an existing directory is
    writable (os.access says so), but is not a file RotatingFileHandler can
    open, so it must be refused exactly like a missing directory is."""
    admin()
    before = config_file.read_text(encoding="utf-8")
    existing_dir = config_file.parent / "logs_dir"
    existing_dir.mkdir()

    response = file_client.post(
        "/admin/api/config/apply",
        json={"edits": {"logging.file.file_name": str(existing_dir)}},
        headers=csrf(file_client),
    )

    assert response.status_code == 422
    assert config_file.read_text(encoding="utf-8") == before
    assert not config_file.with_name("config.toml.bak").exists()


def test_apply_reports_a_degraded_reload_when_setup_logging_fails(
    file_client, admin, app_with_file
):
    """FIX B regression guard: a failure re-applying logging inside hot_reload
    must not surface as a 500 for a write that already committed, and the
    config swap must still go through -- the alternative is a process that
    silently keeps running the OLD config while believing it is running the
    new one."""
    admin()

    new_factory = MagicMock()
    new_factory.init_clients = MagicMock()
    new_factory.close_clients = AsyncMock()
    with (
        patch("testbench_ai_service.webui.reload.LLMFactory", MagicMock(return_value=new_factory)),
        patch(
            "testbench_ai_service.webui.reload.setup_logging",
            side_effect=ValueError("Unable to configure handler 'file'"),
        ),
    ):
        response = file_client.post(
            "/admin/api/config/apply",
            json={"edits": {"language": "en"}},
            headers=csrf(file_client),
        )

    assert response.status_code == 200
    body = response.json()
    assert body["reloaded"] is False
    assert body["reload_detail"]
    assert app_with_file.state.config.language.value == "en"


def test_apply_reports_a_post_write_reread_failure_without_raising(file_client, admin, config_file):
    """FIX C/D: the write already committed by the time re-reading the file
    to verify the reload can fail, so that failure must come back as a
    normal 200 with the reason named in reload_detail, never a 4xx that
    would falsely imply the apply itself failed."""
    admin()
    calls = {"count": 0}

    def flaky_read(path):
        calls["count"] += 1
        if calls["count"] == 1:
            # The read _plan_change makes before anything is written must
            # still succeed, or nothing would ever get written to fail the
            # re-read against in the first place.
            return read_config_file(path)
        raise HTTPException(status_code=400, detail="not valid TOML: boom")

    with patch("testbench_ai_service.webui.routes.read_config_file", side_effect=flaky_read):
        response = file_client.post(
            "/admin/api/config/apply",
            json={"edits": {"language": "en"}},
            headers=csrf(file_client),
        )

    assert response.status_code == 200
    body = response.json()
    assert body["reloaded"] is False
    assert body["reload_detail"]
    assert "boom" in body["reload_detail"]
    assert 'language = "en"' in config_file.read_text(encoding="utf-8")


def test_status_reports_no_restart_needed_when_disk_matches_the_process(file_client, admin):
    admin()

    body = file_client.get("/admin/api/status").json()

    assert body["restart_required"] == []


def test_status_reports_a_restart_after_a_boot_fixed_change_is_written(
    file_client, admin, config_file
):
    admin()

    file_client.post(
        "/admin/api/config/apply",
        json={"edits": {"port": 9999}},
        headers=csrf(file_client),
    )
    body = file_client.get("/admin/api/status").json()

    assert body["restart_required"] == ["port"]


def test_status_reports_a_restart_for_a_hand_edited_file(file_client, admin, config_file):
    """An operator editing config.toml by hand must see the banner too."""
    admin()
    config_file.write_text(COMMENTED.replace("port = 8010", "port = 7777"), encoding="utf-8")

    body = file_client.get("/admin/api/status").json()

    assert body["restart_required"] == ["port"]


def test_status_reports_no_restart_after_a_hot_swappable_apply(file_client, admin):
    admin()

    file_client.post(
        "/admin/api/config/apply",
        json={"edits": {"language": "en"}},
        headers=csrf(file_client),
    )
    body = file_client.get("/admin/api/status").json()

    assert body["restart_required"] == []


def test_status_survives_an_invalid_file_on_disk(file_client, admin, config_file):
    """A hand-edit that broke the file must not 500 the status screen."""
    admin()
    config_file.write_text('[testbench-ai-service]\nport = "not a number"\n', encoding="utf-8")

    response = file_client.get("/admin/api/status")

    assert response.status_code == 200
    assert response.json()["restart_required"] == []
