"""``GET /projects`` and ``POST /projects/refresh``, plus the login-time fetch."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from testbench_ai_service.webui.session import CSRF_COOKIE, CSRF_HEADER


def _payload(*projects: dict) -> dict:
    return {"projects": list(projects)}


@pytest.fixture
def tb_connection(tb_connection):
    """The shared stand-in, taught to answer the project list."""
    tb_connection.get_all_projects.return_value = _payload(
        {"name": "Alpha", "key": "11"}, {"name": "Release 2.0", "key": "12"}
    )
    return tb_connection


# --- the login-time fetch ------------------------------------------------


def test_login_caches_the_project_list_on_the_session(client, login):
    login()
    body = client.get("/admin/api/projects").json()
    assert [p["name"] for p in body["projects"]] == ["Alpha", "Release 2.0"]
    assert body["source"] == "testbench"
    assert body["error"] is None
    assert body["fetched_at"] is not None


def test_login_fetches_projects_before_closing_the_connection(login, tb_connection):
    """The whole point of fetching at login is to reuse the connection that is
    already open and authenticated. Fetching after ``close()`` would either fail
    or silently re-authenticate."""
    login()
    names = [
        call[0] for call in tb_connection.mock_calls if call[0] in ("get_all_projects", "close")
    ]
    assert names.index("get_all_projects") < names.index("close")


def test_login_opens_exactly_one_connection(login, tb_connection):
    """One outbound connection per login (design D3): the stored token may be
    the operator's plaintext password, so it is used as rarely as possible."""
    with patch("testbench_ai_service.webui.projects.TBConnection") as refresh_conn_cls:
        login()
    refresh_conn_cls.assert_not_called()


def test_a_failed_projects_fetch_still_signs_the_operator_in(client, login, tb_connection):
    """Editing service, LLM or logging settings must not depend on an unrelated
    TestBench endpoint (design D4)."""
    tb_connection.get_all_projects.side_effect = requests.exceptions.Timeout("slow")
    response = login()
    assert response.status_code == 200
    assert response.json()["username"] == "a.mueller"


def test_a_failed_projects_fetch_is_recorded_on_the_session(client, login, tb_connection):
    tb_connection.get_all_projects.side_effect = requests.exceptions.Timeout("slow")
    login()
    body = client.get("/admin/api/projects").json()
    assert body["projects"] == []
    assert body["source"] == "unavailable"
    assert "slow" in body["error"]
    assert body["fetched_at"] is not None


def test_a_projects_fetch_that_raises_an_unexpected_error_still_signs_in(
    client, login, tb_connection
):
    """The vendored client indexes into its own JSON without checking, so an
    unexpected payload raises KeyError from inside the library."""
    tb_connection.get_all_projects.side_effect = KeyError("projects")
    assert login().status_code == 200
    assert client.get("/admin/api/projects").json()["source"] == "unavailable"


def test_login_does_not_report_projects_in_its_own_response(login):
    """The login payload is identity only. The list has a route of its own so a
    stale cache can be refreshed without re-authenticating."""
    assert "projects" not in login().json()


# --- GET /projects -------------------------------------------------------


def test_get_projects_without_a_session_is_401(client):
    assert client.get("/admin/api/projects").status_code == 401


def test_get_projects_is_open_to_a_non_admin(client, login):
    """Reading the configuration surface is open to everyone signed in; only
    the mutating routes require the admin role."""
    login(roles=["ProjectUser"])
    assert client.get("/admin/api/projects").status_code == 200


def test_get_projects_never_leaks_the_testbench_token(client, login):
    login()
    response = client.get("/admin/api/projects")
    assert "tb-token-abc" not in response.text


def test_get_projects_makes_no_outbound_call(client, login):
    """It is a read of the cache. If it re-fetched, every page load would spend
    the stored credential again."""
    login()
    with patch("testbench_ai_service.webui.projects.TBConnection") as conn_cls:
        assert client.get("/admin/api/projects").status_code == 200
    conn_cls.assert_not_called()


# --- POST /projects/refresh ---------------------------------------------


def _refresh_connection(*projects: dict) -> MagicMock:
    conn = MagicMock()
    conn.get_all_projects.return_value = _payload(*projects)
    return conn


def test_refresh_replaces_the_cached_list(client, login):
    csrf = login().cookies[CSRF_COOKIE]
    conn = _refresh_connection({"name": "Gamma", "key": "13"})
    with patch("testbench_ai_service.webui.projects.TBConnection", return_value=conn):
        body = client.post("/admin/api/projects/refresh", headers={CSRF_HEADER: csrf}).json()
    assert [p["name"] for p in body["projects"]] == ["Gamma"]
    assert body["source"] == "testbench"
    # And the replacement is what the next plain read sees.
    assert [p["name"] for p in client.get("/admin/api/projects").json()["projects"]] == ["Gamma"]


def test_refresh_authenticates_with_the_stored_token_not_a_password(client, login):
    csrf = login().cookies[CSRF_COOKIE]
    conn = _refresh_connection({"name": "Gamma", "key": "13"})
    with patch("testbench_ai_service.webui.projects.TBConnection", return_value=conn) as conn_cls:
        client.post("/admin/api/projects/refresh", headers={CSRF_HEADER: csrf})
    assert conn_cls.call_args.kwargs["sessionToken"] == "tb-token-abc"
    conn.close.assert_called_once()


def test_refresh_requires_the_admin_role(client, login):
    csrf = login(roles=["ProjectUser"]).cookies[CSRF_COOKIE]
    response = client.post("/admin/api/projects/refresh", headers={CSRF_HEADER: csrf})
    assert response.status_code == 403


def test_refresh_requires_the_csrf_header(client, login):
    login()
    assert client.post("/admin/api/projects/refresh").status_code == 403


def test_refresh_with_a_wrong_csrf_token_is_403(client, login):
    login()
    response = client.post("/admin/api/projects/refresh", headers={CSRF_HEADER: "nope"})
    assert response.status_code == 403


def test_refresh_without_a_session_is_401(client):
    assert client.post("/admin/api/projects/refresh").status_code == 401


def test_a_failed_refresh_is_a_200_reporting_unavailable(client, login):
    """A refresh that could not reach TestBench is a fact about TestBench, not a
    failure of the console -- and the operator still needs the rest of the
    screen to work."""
    csrf = login().cookies[CSRF_COOKIE]
    conn = MagicMock()
    conn.get_all_projects.side_effect = requests.exceptions.ConnectionError("no route")
    with patch("testbench_ai_service.webui.projects.TBConnection", return_value=conn):
        response = client.post("/admin/api/projects/refresh", headers={CSRF_HEADER: csrf})
    assert response.status_code == 200
    assert response.json()["source"] == "unavailable"
    assert "no route" in response.json()["error"]


def test_a_failed_refresh_keeps_the_list_it_could_not_replace(client, login):
    csrf = login().cookies[CSRF_COOKIE]
    conn = MagicMock()
    conn.get_all_projects.side_effect = requests.exceptions.ConnectionError("no route")
    with patch("testbench_ai_service.webui.projects.TBConnection", return_value=conn):
        body = client.post("/admin/api/projects/refresh", headers={CSRF_HEADER: csrf}).json()
    assert [p["name"] for p in body["projects"]] == ["Alpha", "Release 2.0"]
