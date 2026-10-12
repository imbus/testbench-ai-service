import json
from pathlib import Path

import pytest

from testbench_ai_service.models.logging import ActivityLoggerConfig
from testbench_ai_service.webui.activity import read_activity


def _entry(message, scope, user_key=None, level="INFO", **extra):
    return json.dumps(
        {
            "ts": "2026-10-13T10:00:00.000+00:00",
            "level": level,
            "source": "testbench_ai_service",
            "message": message,
            "scope": scope,
            "user_key": user_key,
            "username": "someone" if user_key else None,
            "project_key": None,
            "run_id": None,
            "agent": None,
            **extra,
        }
    )


def _write(path: Path, *lines: str) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.fixture
def cfg(tmp_path):
    return ActivityLoggerConfig(file_name=str(tmp_path / "act.jsonl"), backup_count=2)


def _read(cfg, **kw):
    args = {
        "user_key": "me",
        "include_own": True,
        "include_service": False,
        "min_level": 20,
        "limit": 50,
    }
    args.update(kw)
    return [e.message for e in read_activity(cfg, **args)]


def test_own_entries_newest_first_and_never_others(cfg):
    _write(
        Path(cfg.file_name),
        _entry("mine 1", "user", "me"),
        _entry("theirs", "user", "other"),
        _entry("startup", "service"),
        _entry("mine 2", "user", "me"),
    )
    assert _read(cfg) == ["mine 2", "mine 1"]


def test_service_only_when_asked(cfg):
    _write(Path(cfg.file_name), _entry("startup", "service"), _entry("theirs", "user", "other"))
    assert _read(cfg, include_service=True) == ["startup"]
    assert _read(cfg, include_own=False, include_service=True) == ["startup"]


def test_request_scope_is_never_returned(cfg):
    _write(Path(cfg.file_name), _entry("body", "request"), _entry("odd", "request", "me"))
    assert _read(cfg, include_service=True) == []


def test_no_user_key_means_no_own_entries(cfg):
    # Review Focus 3.
    _write(Path(cfg.file_name), _entry("ghost", "user", None), _entry("x", "user", "me"))
    assert _read(cfg, user_key=None) == []


def test_filter_runs_before_limit(cfg):
    lines = [_entry("mine", "user", "me")] * 5 + [_entry("theirs", "user", "other")] * 600
    _write(Path(cfg.file_name), *lines)
    assert len(_read(cfg, limit=50)) == 5


def test_level_floor(cfg):
    _write(
        Path(cfg.file_name),
        _entry("dbg", "user", "me", level="DEBUG"),
        _entry("err", "user", "me", level="ERROR"),
    )
    assert _read(cfg, min_level=30) == ["err"]


def test_reads_rotated_backups_newest_first(cfg):
    # Review Focus 4.
    base = Path(cfg.file_name)
    _write(base.with_name(base.name + ".2"), _entry("oldest", "user", "me"))
    _write(base.with_name(base.name + ".1"), _entry("older", "user", "me"))
    _write(base, _entry("newest", "user", "me"))
    assert _read(cfg) == ["newest", "older", "oldest"]


def test_missing_file_and_garbage_lines(cfg):
    # Review Focus 4.
    assert _read(cfg) == []
    _write(
        Path(cfg.file_name),
        "not json",
        "[1, 2]",
        json.dumps({"scope": "user", "user_key": "me"}),
        _entry("list level", "user", "me", level=["INFO"]),
        _entry("dict level", "user", "me", level={"x": 1}),
        _entry("ok", "user", "me"),
    )
    assert _read(cfg) == ["ok"]


def test_disabled_sink_returns_nothing(cfg):
    _write(Path(cfg.file_name), _entry("x", "user", "me"))
    assert _read(cfg.model_copy(update={"enabled": False})) == []


# --- endpoint ---------------------------------------------------------------


@pytest.fixture
def sink(client, tmp_path):
    path = tmp_path / "act.jsonl"
    client.app.state.config.logging.activity.file_name = str(path)
    _write(
        path,
        _entry("startup", "service"),
        _entry("mine", "user", "u-1"),
        _entry("theirs", "user", "u-2"),
        _entry("body", "request"),
    )
    return path


def _messages(response):
    assert response.status_code == 200
    return [e["message"] for e in response.json()]


def test_endpoint_requires_a_session(client):
    assert client.get("/admin/api/activity").status_code == 401


def test_non_admin_sees_only_own_even_when_asking_for_all(client, login, sink):
    login(roles=["Project User"])
    assert _messages(client.get("/admin/api/activity?scope=all")) == ["mine"]
    assert _messages(client.get("/admin/api/activity?scope=service")) == ["mine"]


def test_admin_sees_own_and_service_never_other_users(client, login, sink):
    login()
    assert _messages(client.get("/admin/api/activity")) == ["mine", "startup"]
    assert _messages(client.get("/admin/api/activity?scope=mine")) == ["mine"]
    assert _messages(client.get("/admin/api/activity?scope=service")) == ["startup"]


def test_admin_without_user_key_sees_only_service(client, login, sink, tb_connection):
    # Review Focus 3.
    tb_connection.session.get.side_effect = ValueError("TB3")
    login()
    assert _messages(client.get("/admin/api/activity")) == ["startup"]


def test_response_never_names_users(client, login, sink):
    login()
    for entry in client.get("/admin/api/activity").json():
        assert "user_key" not in entry
        assert "username" not in entry


def test_unknown_query_user_key_is_ignored(client, login, sink):
    login(roles=["Project User"])
    assert _messages(client.get("/admin/api/activity?user_key=u-2")) == ["mine"]


def test_limit_is_bounded(client, login):
    login()
    assert client.get("/admin/api/activity?limit=100000").status_code == 422


def test_old_log_endpoint_is_gone(client, login):
    login()
    assert client.get("/admin/api/logs").status_code == 404


def test_status_no_longer_reports_the_log_file(client, login):
    login()
    assert "log_file" not in client.get("/admin/api/status").json()
