from unittest.mock import patch

import pytest
import requests
from fastapi import HTTPException
from fastapi.testclient import TestClient

from testbench_ai_service.models.webui import AdminUiConfig
from testbench_ai_service.webui.auth import require_admin
from testbench_ai_service.webui.session import (
    CSRF_COOKIE,
    CSRF_HEADER,
    SESSION_COOKIE,
    SessionStore,
)


def _find_set_cookie(response, cookie_name: str) -> str:
    """Return the one Set-Cookie header that sets *cookie_name*.

    ``response.headers.items()`` can collapse duplicate headers, so this reads
    the raw list and locates the header for this specific cookie rather than
    concatenating every Set-Cookie header together.
    """
    headers = response.headers.get_list("set-cookie")
    matches = [h for h in headers if h.startswith(f"{cookie_name}=")]
    assert matches, f"no Set-Cookie header for {cookie_name!r} among {headers!r}"
    return matches[0]


def test_login_sets_both_cookies(login):
    response = login()
    assert response.status_code == 200
    assert SESSION_COOKIE in response.cookies
    assert CSRF_COOKIE in response.cookies


def test_login_returns_identity_not_secrets(login):
    body = login().json()
    assert body["username"] == "a.mueller"
    assert body["is_admin"] is True
    assert body["roles"] == ["Administrator"]
    # The TestBench token must never reach the browser.
    assert "tb-token-abc" not in str(body)


def test_session_cookie_is_httponly_and_strict(login):
    """The opaque session id must be unreadable to page JavaScript.

    Asserted against the SESSION_COOKIE header specifically, not against the
    concatenation of every Set-Cookie header -- that weaker form would still
    pass if HttpOnly landed on the wrong cookie.
    """
    response = login()
    header = _find_set_cookie(response, SESSION_COOKIE)
    assert "httponly" in header.lower()
    assert "samesite=strict" in header.lower().replace(" ", "")


def test_csrf_cookie_is_readable_by_script(login):
    """The SPA has to read this one to echo it back, so it must NOT be
    HttpOnly -- asserted against the CSRF_COOKIE header specifically."""
    response = login()
    header = _find_set_cookie(response, CSRF_COOKIE)
    assert "httponly" not in header.lower()
    assert "samesite=strict" in header.lower().replace(" ", "")


def test_non_admin_login_reports_not_admin(login):
    body = login(roles=["ProjectUser"]).json()
    assert body["is_admin"] is False


def test_project_user_with_space_is_not_admin(login):
    """The TestBench 3 path can answer 'Project User' with a space."""
    assert login(roles=["Project User"]).json()["is_admin"] is False


def test_bad_credentials_return_401(client, tb_connection):
    error = requests.exceptions.HTTPError(response=type("R", (), {"status_code": 401})())
    tb_connection.read_user_roles.side_effect = error
    with patch("testbench_ai_service.webui.auth.TBConnection", return_value=tb_connection):
        response = client.post("/admin/api/session", json={"username": "a", "password": "wrong"})
    assert response.status_code == 401
    assert SESSION_COOKIE not in response.cookies


def test_malformed_server_url_is_a_config_error_not_a_401(client):
    """TBConnection raises ValueError for a URL without an explicit port."""
    with patch(
        "testbench_ai_service.webui.auth.TBConnection",
        side_effect=ValueError("Invalid server URL"),
    ):
        response = client.post("/admin/api/session", json={"username": "a", "password": "pw"})
    assert response.status_code == 500
    assert "configuration" in response.json()["detail"].lower()


def test_get_session_without_cookie_is_401(client):
    assert client.get("/admin/api/session").status_code == 401


def test_get_session_after_login_returns_identity(client, login):
    login()
    response = client.get("/admin/api/session")
    assert response.status_code == 200
    assert response.json()["username"] == "a.mueller"
    assert response.json()["tb_server_url"].endswith("/api/")


def test_logout_revokes_the_session(client, login):
    csrf = login().cookies[CSRF_COOKIE]
    assert client.delete("/admin/api/session", headers={CSRF_HEADER: csrf}).status_code == 204
    assert client.get("/admin/api/session").status_code == 401


def test_logout_without_csrf_header_is_403(client, login):
    login()
    assert client.delete("/admin/api/session").status_code == 403


def test_logout_with_wrong_csrf_token_is_403(client, login):
    login()
    assert (
        client.delete("/admin/api/session", headers={CSRF_HEADER: "not-the-token"}).status_code
        == 403
    )


def test_unknown_session_cookie_is_401(client):
    client.cookies.set(SESSION_COOKIE, "forged")
    assert client.get("/admin/api/session").status_code == 401


def test_meta_is_reachable_without_a_session(client):
    """The login screen must be able to name the TestBench server."""
    response = client.get("/admin/api/meta")
    assert response.status_code == 200
    assert response.json()["tb_server_url"] == "https://localhost:9443/api/"


def test_meta_exposes_nothing_else(client):
    assert set(client.get("/admin/api/meta").json()) == {"tb_server_url"}


def test_require_admin_accepts_an_admin():
    session = SessionStore().create(
        username="a", roles=["Administrator"], is_admin=True, tb_session_token="t"
    )
    assert require_admin(session) is session


def test_require_admin_refuses_a_non_admin():
    session = SessionStore().create(
        username="p", roles=["ProjectUser"], is_admin=False, tb_session_token="t"
    )
    with pytest.raises(HTTPException) as exc:
        require_admin(session)
    assert exc.value.status_code == 403


def test_require_loopback_refuses_remote_client(make_app, tb_connection):
    app = make_app(admin_ui=AdminUiConfig(require_loopback=True))
    with (
        TestClient(app, client=("10.0.0.9", 5000), raise_server_exceptions=False) as c,
        patch("testbench_ai_service.webui.auth.TBConnection", return_value=tb_connection),
    ):
        response = c.post("/admin/api/session", json={"username": "a", "password": "pw"})
    assert response.status_code == 403
