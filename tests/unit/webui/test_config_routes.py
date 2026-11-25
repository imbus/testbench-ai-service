from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from testbench_ai_service.webui.config_io import REDACTED_SENTINEL
from testbench_ai_service.webui.plan import plan_change

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


def test_preview_of_a_port_outside_the_tcp_range_reports_an_issue(file_client, admin):
    admin()

    body = file_client.post(
        "/admin/api/config/preview",
        json={"edits": {"port": 99999}},
        headers=csrf(file_client),
    ).json()

    assert body["valid"] is False
    assert [issue["path"] for issue in body["issues"]] == ["port"]


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

    _preview, text_to_write, _has_write = plan_change(
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


def test_apply_of_only_a_credential_change_still_writes(
    credentialed_client, credentialed_admin, credentialed_config_file
):
    """FIX 3 regression: the write decision must be made on the RAW before/after
    text, not on the redacted `diffs`. Changing an existing credential value to
    a different one redacts identically on both sides of the diff (both show
    the sentinel), so the DISPLAYED diff is empty -- but that must not be read
    as "nothing to write", or the operator's change would be silently
    discarded. The real new value must land in the file and the sentinel must
    never be written.
    """
    credentialed_admin()

    body = credentialed_client.post(
        "/admin/api/config/apply",
        json={"edits": {"llm_config.api_key": "sk-NEW-REAL-SECRET"}},
        headers=csrf(credentialed_client),
    ).json()

    assert body["written"] == [str(credentialed_config_file.resolve())]
    written = credentialed_config_file.read_text(encoding="utf-8")
    assert "sk-NEW-REAL-SECRET" in written
    assert REDACTED_SENTINEL not in written


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

    def flaky_read(path):
        # Only the re-read in the route fails: plan_change (webui.plan) reads
        # the file through its own import, so something gets written first.
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


def test_apply_keeps_the_crlf_line_endings_of_the_file(file_client, admin, config_file):
    config_file.write_bytes(COMMENTED.replace("\n", "\r\n").encode("utf-8"))
    admin()
    edits = {"edits": {"port": 9999, "language": "de"}}

    preview = file_client.post(
        "/admin/api/config/preview", json=edits, headers=csrf(file_client)
    ).json()
    file_client.post("/admin/api/config/apply", json=edits, headers=csrf(file_client))

    written = config_file.read_bytes()
    assert b"port = 9999\r\n" in written
    assert b'language = "de"\r\n' in written
    assert written.count(b"\r\n") == written.count(b"\n")
    # The browser is shown LF only: a CR in the diff would render as a stray character.
    assert "\r" not in preview["toml"]
    assert all("\r" not in diff["diff"] for diff in preview["diffs"])
    assert preview["diffs"][0]["added"] == 2


def test_apply_keeps_the_lf_line_endings_of_the_file(file_client, admin, config_file):
    config_file.write_bytes(COMMENTED.encode("utf-8"))
    admin()

    file_client.post(
        "/admin/api/config/apply",
        json={"edits": {"port": 9999}},
        headers=csrf(file_client),
    )

    assert b"\r" not in config_file.read_bytes()


def _preview_restart(client, edits) -> list[str]:
    response = client.post("/admin/api/config/preview", json={"edits": edits}, headers=csrf(client))
    assert response.status_code == 200, response.text
    return response.json()["restart_required"]


def test_the_app_knows_which_agents_got_a_route(app_with_file):
    assert "test_case_set_reviewer" in app_with_file.state.routed_agents
    assert "test_planner" not in app_with_file.state.routed_agents


def test_an_agent_disabled_while_running_can_be_enabled_again_without_a_restart(file_client, admin):
    admin()
    key = "agents.test_case_set_reviewer.enabled"
    applied = file_client.post(
        "/admin/api/config/apply", json={"edits": {key: False}}, headers=csrf(file_client)
    ).json()

    assert applied["restart_required"] == []
    assert _preview_restart(file_client, {key: True}) == []


def test_enabling_an_agent_that_got_no_route_at_startup_needs_a_restart(
    file_client, admin, app_with_file
):
    admin()
    key = "agents.test_case_set_reviewer.enabled"
    file_client.post(
        "/admin/api/config/apply", json={"edits": {key: False}}, headers=csrf(file_client)
    )
    # As after a start with the agent disabled: no route was registered for it.
    app_with_file.state.routed_agents = frozenset()

    assert _preview_restart(file_client, {key: True}) == [key]
    applied = file_client.post(
        "/admin/api/config/apply", json={"edits": {key: True}}, headers=csrf(file_client)
    ).json()
    assert applied["restart_required"] == [key]
    status = file_client.get("/admin/api/status").json()
    assert key in status["restart_required"]


def test_a_non_admin_can_read_the_raw_file(file_client, admin, config_file):
    admin(roles=["ProjectUser"])

    response = file_client.get("/admin/api/config/raw")

    assert response.status_code == 200
    assert response.json()["toml"] == COMMENTED


def test_the_raw_file_hides_credentials(file_client, admin, config_file):
    config_file.write_text(CREDENTIALED, encoding="utf-8")
    admin(roles=["ProjectUser"])

    toml = file_client.get("/admin/api/config/raw").json()["toml"]

    assert "sk-REAL-SECRET-VALUE" not in toml
    assert REDACTED_SENTINEL in toml
    assert "# Provider credential -- must never leave this file." in toml


def test_the_raw_file_needs_a_session(file_client):
    assert file_client.get("/admin/api/config/raw").status_code == 401


PLANNER = (
    COMMENTED
    + """
[testbench-ai-service.agents.test_planner]
enabled = false
endpoint_path = "/test-planner"
class_path = "testbench_ai_service.agents.test_planner.agent.TestPlannerAgent"

[testbench-ai-service.agents.test_planner.prompt]
file = "test_planner/prompt.yaml"
"""
)
KNEE = "agents.test_planner.prompt.vars.knee_percent"


def _preview(client, edits) -> dict:
    response = client.post("/admin/api/config/preview", json={"edits": edits}, headers=csrf(client))
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize("value", [-5.75, 0, "abc", True])
def test_a_number_variable_outside_its_declaration_is_refused(
    file_client, admin, config_file, value
):
    config_file.write_text(PLANNER, encoding="utf-8")
    admin()

    preview = _preview(file_client, {KNEE: value})

    assert preview["valid"] is False
    assert [issue["path"] for issue in preview["issues"]] == [KNEE]
    applied = file_client.post(
        "/admin/api/config/apply", json={"edits": {KNEE: value}}, headers=csrf(file_client)
    )
    assert applied.status_code == 422
    assert config_file.read_text(encoding="utf-8") == PLANNER


@pytest.mark.parametrize("value", [1, 100, 150.5])
def test_a_number_variable_within_its_declaration_is_accepted(
    file_client, admin, config_file, value
):
    config_file.write_text(PLANNER, encoding="utf-8")
    admin()

    assert _preview(file_client, {KNEE: value})["valid"] is True


def test_a_project_override_of_a_variable_is_checked_too(file_client, admin, config_file):
    config_file.write_text(PLANNER, encoding="utf-8")
    admin()
    quoted = 'projects."Projekt A".agents.test_planner.prompt.vars.knee_percent'

    for path in (quoted, quoted.replace('"', "")):
        preview = _preview(file_client, {path: -1})

        assert preview["valid"] is False
        assert [issue["path"] for issue in preview["issues"]] == [quoted.replace('"', "")]


def test_a_bad_variable_already_in_the_file_does_not_block_another_change(
    file_client, admin, config_file
):
    config_file.write_text(
        PLANNER + "\n[testbench-ai-service.agents.test_planner.prompt.vars]\nknee_percent = -5\n",
        encoding="utf-8",
    )
    admin()

    assert _preview(file_client, {"language": "de"})["valid"] is True


def test_the_config_carries_what_the_file_amounts_to(file_client, admin, app_with_file):
    """`effective` is the file with defaults: it follows a change the running
    process has not taken up, which `running` cannot."""
    admin()
    file_client.post(
        "/admin/api/config/apply", json={"edits": {"port": 9999}}, headers=csrf(file_client)
    )

    body = file_client.get("/admin/api/config").json()

    assert body["disk"]["port"] == 9999
    assert body["running"]["port"] == 8010
    assert body["effective"]["port"] == 9999
    # A key the file does not set shows its default there, not nothing.
    assert body["effective"]["host"] == body["running"]["host"]


def test_the_effective_config_falls_back_when_the_file_is_unusable(file_client, admin, config_file):
    admin()
    config_file.write_text(COMMENTED.replace("port = 8010", "port = 0"), encoding="utf-8")

    body = file_client.get("/admin/api/config").json()

    assert body["effective"] == body["running"]
