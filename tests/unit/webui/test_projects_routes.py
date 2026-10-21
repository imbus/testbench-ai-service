"""``GET /projects`` and ``POST /projects/refresh``, plus the login-time fetch."""

import inspect
from unittest.mock import MagicMock, patch

import pytest
import requests

from testbench_ai_service.webui.routes import sign_in
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


def test_login_keeps_the_connection_open(login, tb_connection):
    """Closing the login connection stops its heartbeat, and TestBench 4 then
    drops the session token after about five minutes -- every later call on
    it would fail."""
    login()
    tb_connection.get_all_projects.assert_called_once()
    tb_connection.close.assert_not_called()


def test_login_opens_exactly_one_connection(client, tb_connection):
    with patch(
        "testbench_ai_service.webui.tb_link.TBConnection", return_value=tb_connection
    ) as conn_cls:
        client.post("/admin/api/session", json={"username": "a.mueller", "password": "pw"})
    conn_cls.assert_called_once()


def test_logout_closes_the_login_connection(client, login, tb_connection):
    csrf = login().cookies[CSRF_COOKIE]
    client.delete("/admin/api/session", headers={CSRF_HEADER: csrf})
    tb_connection.close.assert_called_once()


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


def test_get_projects_makes_no_outbound_call(client, login, tb_connection):
    """It is a read of the cache. If it re-fetched, every page load would cost
    a TestBench round-trip."""
    login()
    tb_connection.get_all_projects.reset_mock()
    assert client.get("/admin/api/projects").status_code == 200
    tb_connection.get_all_projects.assert_not_called()


# --- POST /projects/refresh ---------------------------------------------


def _unauthorized() -> requests.exceptions.HTTPError:
    response = requests.Response()
    response.status_code = 401
    return requests.exceptions.HTTPError("401", response=response)


def test_refresh_replaces_the_cached_list(client, login, tb_connection):
    csrf = login().cookies[CSRF_COOKIE]
    tb_connection.get_all_projects.return_value = _payload({"name": "Gamma", "key": "13"})
    body = client.post("/admin/api/projects/refresh", headers={CSRF_HEADER: csrf}).json()
    assert [p["name"] for p in body["projects"]] == ["Gamma"]
    assert body["source"] == "testbench"
    # And the replacement is what the next plain read sees.
    assert [p["name"] for p in client.get("/admin/api/projects").json()["projects"]] == ["Gamma"]


def test_refresh_reuses_the_live_login_connection(client, login, tb_connection):
    csrf = login().cookies[CSRF_COOKIE]
    with patch("testbench_ai_service.webui.tb_link.TBConnection") as conn_cls:
        client.post("/admin/api/projects/refresh", headers={CSRF_HEADER: csrf})
    conn_cls.assert_not_called()
    tb_connection.close.assert_not_called()


def _fresh_login_connection(*projects: dict) -> MagicMock:
    conn = MagicMock()
    conn.session_token = "tb-token-new"
    conn.session_terminated = False
    conn.read_user_roles.return_value = ["Administrator"]
    conn.get_all_projects.return_value = _payload(*projects)
    return conn


def test_refresh_logs_in_again_when_the_heartbeat_lost_the_session(client, login, tb_connection):
    """The bug this guards: TestBench ended the session (token idle past five
    minutes, server restart, ...). The refresh must renew it rather than fail."""
    csrf = login(password="pw").cookies[CSRF_COOKIE]
    tb_connection.session_terminated = True
    fresh = _fresh_login_connection({"name": "Gamma", "key": "13"})
    with patch("testbench_ai_service.webui.tb_link.TBConnection", return_value=fresh) as conn_cls:
        body = client.post("/admin/api/projects/refresh", headers={CSRF_HEADER: csrf}).json()
    assert body["source"] == "testbench"
    assert [p["name"] for p in body["projects"]] == ["Gamma"]
    assert conn_cls.call_args.kwargs["loginname"] == "a.mueller"
    assert conn_cls.call_args.kwargs["password"] == "pw"
    tb_connection.close.assert_called_once()


def test_refresh_logs_in_again_on_a_401_the_heartbeat_has_not_seen_yet(
    client, login, tb_connection
):
    csrf = login().cookies[CSRF_COOKIE]
    tb_connection.get_all_projects.side_effect = _unauthorized()
    fresh = _fresh_login_connection({"name": "Gamma", "key": "13"})
    with patch("testbench_ai_service.webui.tb_link.TBConnection", return_value=fresh):
        body = client.post("/admin/api/projects/refresh", headers={CSRF_HEADER: csrf}).json()
    assert body["source"] == "testbench"
    assert [p["name"] for p in body["projects"]] == ["Gamma"]


def test_the_renewed_connection_is_the_one_logout_closes(client, login, tb_connection):
    csrf = login().cookies[CSRF_COOKIE]
    tb_connection.session_terminated = True
    fresh = _fresh_login_connection()
    with patch("testbench_ai_service.webui.tb_link.TBConnection", return_value=fresh):
        client.post("/admin/api/projects/refresh", headers={CSRF_HEADER: csrf})
    client.delete("/admin/api/session", headers={CSRF_HEADER: csrf})
    fresh.close.assert_called_once()


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


def test_a_failed_refresh_is_a_200_reporting_unavailable(client, login, tb_connection):
    """A refresh that could not reach TestBench is a fact about TestBench, not a
    failure of the console -- and the operator still needs the rest of the
    screen to work."""
    csrf = login().cookies[CSRF_COOKIE]
    tb_connection.get_all_projects.side_effect = requests.exceptions.ConnectionError("no route")
    response = client.post("/admin/api/projects/refresh", headers={CSRF_HEADER: csrf})
    assert response.status_code == 200
    assert response.json()["source"] == "unavailable"
    assert "no route" in response.json()["error"]


def test_a_failed_refresh_keeps_the_list_it_could_not_replace(client, login, tb_connection):
    csrf = login().cookies[CSRF_COOKIE]
    tb_connection.get_all_projects.side_effect = requests.exceptions.ConnectionError("no route")
    body = client.post("/admin/api/projects/refresh", headers={CSRF_HEADER: csrf}).json()
    assert [p["name"] for p in body["projects"]] == ["Alpha", "Release 2.0"]


def test_the_login_route_runs_in_the_threadpool():
    """Not a style point: the route makes two blocking TestBench calls.

    Phase 3 added the project fetch to a login that was already blocking, so
    an `async def` would hold the event loop for the authentication *and* the
    list -- with retries, up to minutes. Starlette runs a sync `def` endpoint
    in the threadpool instead.
    """
    assert not inspect.iscoroutinefunction(sign_in)


# --- project admins --------------------------------------------------------


def test_project_admin_can_refresh_projects(client, login_project_admin):
    csrf = login_project_admin(managed=["Alpha"]).cookies[CSRF_COOKIE]
    response = client.post("/admin/api/projects/refresh", headers={CSRF_HEADER: csrf})
    assert response.status_code == 200


def test_refresh_rereads_managed_projects(client, login_project_admin, tb_connection):
    csrf = login_project_admin(managed=["Alpha"]).cookies[CSRF_COOKIE]
    assert client.get("/admin/api/session").json()["managed_projects"] == ["Alpha"]

    original_get = tb_connection.session.get.side_effect

    def _get(url, *args, **kwargs):
        if url.endswith("2/users/self/projectRoles"):
            response = MagicMock()
            response.json.return_value = [
                {
                    "userKey": "u-1",
                    "userLogin": "a.mueller",
                    "userName": "A. Mueller",
                    "projectKey": f"key-{name}",
                    "projectName": name,
                    "roles": ["TestManager"],
                }
                for name in ("Alpha", "Gamma")
            ]
            return response
        return original_get(url, *args, **kwargs)

    tb_connection.session.get.side_effect = _get
    client.post("/admin/api/projects/refresh", headers={CSRF_HEADER: csrf})
    assert client.get("/admin/api/session").json()["managed_projects"] == ["Alpha", "Gamma"]


def test_failed_membership_reread_keeps_the_managed_projects(
    client, login_project_admin, tb_connection
):
    csrf = login_project_admin(managed=["Alpha"]).cookies[CSRF_COOKIE]
    tb_connection.session.get.side_effect = requests.exceptions.ConnectionError("no route")
    response = client.post("/admin/api/projects/refresh", headers={CSRF_HEADER: csrf})
    assert response.status_code == 200
    assert client.get("/admin/api/session").json()["managed_projects"] == ["Alpha"]
