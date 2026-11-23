"""The cached TestBench project list, below the HTTP layer."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from testbench_ai_service.config import AppConfig
from testbench_ai_service.webui.models import ProjectRef
from testbench_ai_service.webui.projects import (
    fetch_projects,
    fetch_projects_with_token,
    parse_projects,
    projects_response,
    record_projects,
)
from testbench_ai_service.webui.session import SessionStore

TB_URL = "https://localhost:9443/api/"


@pytest.fixture
def config() -> AppConfig:
    with patch("testbench_ai_service.config.validate_tb_server_url"):
        return AppConfig(tb_server_url=TB_URL)


@pytest.fixture
def session():
    return SessionStore().create(
        username="a.mueller", roles=["Administrator"], is_admin=True, tb_session_token="tb-token"
    )


def _payload(*projects: dict) -> dict:
    return {"projects": list(projects)}


# --- parse_projects -------------------------------------------------------


def test_parse_keeps_the_name_and_key_of_each_project():
    refs = parse_projects(_payload({"name": "Alpha", "key": "11"}, {"name": "Beta", "key": "12"}))
    assert refs == [ProjectRef(name="Alpha", key="11"), ProjectRef(name="Beta", key="12")]


def test_parse_keeps_the_raw_name_including_dots_and_spaces():
    """The name is what a ``[projects."<name>"]`` block must be keyed by, so it
    must survive verbatim -- not normalised, not slugified."""
    refs = parse_projects(_payload({"name": "Release 2.0", "key": "7"}))
    assert refs[0].name == "Release 2.0"


def test_parse_stringifies_a_numeric_key():
    """TestBench answers keys as strings, but a JSON number here must not turn
    the whole fetch into a validation error."""
    assert parse_projects(_payload({"name": "Alpha", "key": 11}))[0].key == "11"


def test_parse_drops_everything_but_the_name_and_key():
    """``get_all_projects`` is asked with includeTOVs/includeCycles, so each
    entry carries a whole tree. None of it belongs on the session."""
    refs = parse_projects(_payload({"name": "Alpha", "key": "11", "tovs": [{"name": "T"}] * 50}))
    assert refs == [ProjectRef(name="Alpha", key="11")]


def test_parse_skips_an_entry_with_no_name():
    """A nameless project cannot key a config block, so it is unusable here."""
    assert parse_projects(_payload({"key": "11"}, {"name": "Beta", "key": "12"})) == [
        ProjectRef(name="Beta", key="12")
    ]


def test_parse_skips_an_entry_with_no_key():
    assert parse_projects(_payload({"name": "Alpha"}, {"name": "Beta", "key": "12"})) == [
        ProjectRef(name="Beta", key="12")
    ]


def test_parse_tolerates_a_payload_with_no_projects_list():
    assert parse_projects({}) == []


def test_parse_tolerates_a_payload_that_is_not_a_mapping():
    assert parse_projects([{"name": "Alpha", "key": "1"}]) == []


def test_parse_tolerates_a_non_list_projects_value():
    assert parse_projects({"projects": "Alpha"}) == []


def test_parse_skips_a_non_mapping_entry():
    assert parse_projects(_payload("Alpha", {"name": "Beta", "key": "12"})) == [  # type: ignore[arg-type]
        ProjectRef(name="Beta", key="12")
    ]


# --- fetch_projects -------------------------------------------------------


def test_fetch_returns_the_parsed_list_and_no_error():
    conn = MagicMock()
    conn.get_all_projects.return_value = _payload({"name": "Alpha", "key": "11"})
    result = fetch_projects(conn)
    assert result.projects == [ProjectRef(name="Alpha", key="11")]
    assert result.error is None
    assert result.fetched_at is not None


def test_fetch_reports_a_transport_failure_as_an_error_not_an_exception():
    """A TestBench that cannot answer must not be able to fail a login, so this
    layer never raises (design D4)."""
    conn = MagicMock()
    conn.get_all_projects.side_effect = requests.exceptions.ConnectionError("no route")
    result = fetch_projects(conn)
    assert result.projects == []
    assert result.error is not None
    assert "no route" in result.error


def test_fetch_reports_an_http_error_as_an_error():
    conn = MagicMock()
    conn.get_all_projects.side_effect = requests.exceptions.HTTPError("403 Forbidden")
    result = fetch_projects(conn)
    assert result.projects == []
    assert "403" in (result.error or "")


def test_fetch_survives_an_unexpected_exception_from_the_vendored_client():
    """The vendored client raises KeyError/ValueError/AttributeError on payload
    shapes it did not expect. None of them may reach the login route."""
    conn = MagicMock()
    conn.get_all_projects.side_effect = KeyError("projects")
    result = fetch_projects(conn)
    assert result.projects == []
    assert result.error is not None


def test_fetch_records_the_time_even_when_it_failed():
    """The console shows how stale the list is; "never succeeded" still needs a
    timestamp for "we tried and it did not work"."""
    conn = MagicMock()
    conn.get_all_projects.side_effect = requests.exceptions.ConnectionError("down")
    assert fetch_projects(conn).fetched_at is not None


# --- fetch_projects_with_token -------------------------------------------


def test_fetch_with_token_reuses_the_stored_token_and_never_the_password(config):
    with patch("testbench_ai_service.webui.projects.TBConnection") as conn_cls:
        conn_cls.return_value.get_all_projects.return_value = _payload(
            {"name": "Alpha", "key": "11"}
        )
        result = fetch_projects_with_token(config, "tb-token")
    kwargs = conn_cls.call_args.kwargs
    assert kwargs["sessionToken"] == "tb-token"
    assert "password" not in kwargs
    assert result.projects == [ProjectRef(name="Alpha", key="11")]


def test_fetch_with_token_closes_the_connection_even_on_failure(config):
    with patch("testbench_ai_service.webui.projects.TBConnection") as conn_cls:
        conn_cls.return_value.get_all_projects.side_effect = requests.exceptions.Timeout("slow")
        fetch_projects_with_token(config, "tb-token")
    conn_cls.return_value.close.assert_called_once()


def test_fetch_with_token_reports_an_unusable_server_url_as_an_error(config):
    """TBConnection validates the URL shape in its constructor. That is a
    configuration problem, not a reason to 500 a refresh."""
    with patch(
        "testbench_ai_service.webui.projects.TBConnection",
        side_effect=ValueError("Invalid server URL"),
    ):
        result = fetch_projects_with_token(config, "tb-token")
    assert result.projects == []
    assert "Invalid server URL" in (result.error or "")


def test_fetch_with_token_survives_a_connection_that_cannot_be_hardened(config):
    """Setting up the connection is where an unreachable server shows up.

    Reading ``conn.session`` completes the vendored client's lazy setup -- the
    server version read, the authentication, the heartbeat -- so a TestBench
    that is down, or a stored token it no longer accepts, raises there rather
    than in ``get_all_projects``. That must still be a reported failure, not a
    500 out of a function documented never to raise.
    """
    with (
        patch("testbench_ai_service.webui.projects.TBConnection") as conn_cls,
        patch(
            "testbench_ai_service.webui.projects.harden_connection",
            side_effect=requests.exceptions.ConnectionError("server down"),
        ),
    ):
        result = fetch_projects_with_token(config, "tb-token")

    assert result.projects == []
    assert "server down" in (result.error or "")
    conn_cls.return_value.close.assert_called_once()


# --- record_projects / projects_response ---------------------------------


def test_record_replaces_the_whole_cache(session):
    record_projects(session, fetch_projects(_conn_returning({"name": "Alpha", "key": "11"})))
    record_projects(session, fetch_projects(_conn_returning({"name": "Beta", "key": "12"})))
    assert session.projects == [ProjectRef(name="Beta", key="12")]


def test_record_clears_a_previous_error_on_a_successful_refresh(session):
    session.projects_error = "TestBench was unreachable"
    record_projects(session, fetch_projects(_conn_returning({"name": "Alpha", "key": "11"})))
    assert session.projects_error is None


def test_record_keeps_the_last_good_list_when_a_refresh_fails(session):
    """Replacing a working list with an empty one because a refresh timed out
    would take the operator's project columns away for no reason."""
    record_projects(session, fetch_projects(_conn_returning({"name": "Alpha", "key": "11"})))
    conn = MagicMock()
    conn.get_all_projects.side_effect = requests.exceptions.Timeout("slow")
    record_projects(session, fetch_projects(conn))
    assert session.projects == [ProjectRef(name="Alpha", key="11")]
    assert session.projects_error is not None


def test_response_reports_testbench_as_the_source_after_a_good_fetch(session):
    record_projects(session, fetch_projects(_conn_returning({"name": "Alpha", "key": "11"})))
    body = projects_response(session)
    assert body.source == "testbench"
    assert body.error is None
    assert body.fetched_at == session.projects_fetched_at


def test_response_reports_unavailable_when_the_fetch_failed(session):
    conn = MagicMock()
    conn.get_all_projects.side_effect = requests.exceptions.Timeout("slow")
    record_projects(session, fetch_projects(conn))
    body = projects_response(session)
    assert body.source == "unavailable"
    assert body.error is not None


def test_response_reports_unavailable_when_no_fetch_has_happened(session):
    """A session whose login-time fetch never ran must not claim TestBench as
    the source of an empty list -- that is what unlocks the console's
    "add project by name" fallback."""
    body = projects_response(session)
    assert body.source == "unavailable"
    assert body.projects == []
    assert body.fetched_at is None


def _conn_returning(*projects: dict) -> MagicMock:
    conn = MagicMock()
    conn.get_all_projects.return_value = _payload(*projects)
    return conn
