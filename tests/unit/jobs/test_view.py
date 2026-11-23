from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from testbench_ai_service.auth import AuthInfo, AuthType, validate_auth_token
from testbench_ai_service.config import AppConfig
from testbench_ai_service.jobs.view import VIEW_COOKIE, JobViewStore
from testbench_ai_service.main import create_app
from testbench_ai_service.models.language import LanguageOption

TB_URL = "https://localhost:9443/api/"

# The parts of the built page (frontend/job-view.html) the service relies on.
_BUILT_PAGE = (
    '<!doctype html><html lang="de"><head><!--job-view-config-->'
    '<script type="module" src="/jobs/view-assets/assets/job-view-x1.js"></script>'
    '</head><body><div id="root"></div></body></html>'
)


class _Clock:
    def __init__(self) -> None:
        self.moment = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.moment


def _auth_info() -> AuthInfo:
    return AuthInfo(
        auth_type=AuthType.SESSION_TOKEN, token="test-token", user_key="1", conn=MagicMock()
    )


@pytest.fixture(autouse=True)
def built_page(tmp_path):
    """A stand-in for the frontend build, so the tests do not need npm."""
    (tmp_path / "assets").mkdir()
    (tmp_path / "job-view.html").write_text(_BUILT_PAGE, encoding="utf-8")
    (tmp_path / "assets" / "job-view-x1.js").write_text("console.log(1)", encoding="utf-8")
    with patch("testbench_ai_service.jobs.view.JOB_VIEW_DIR", tmp_path):
        yield tmp_path


@pytest.fixture
def app():
    with (
        patch("testbench_ai_service.config.validate_tb_server_url"),
        patch("testbench_ai_service.main.LLMFactory") as factory_cls,
    ):
        factory = MagicMock()
        factory.close_clients = AsyncMock()
        factory_cls.return_value = factory
        return create_app(AppConfig(tb_server_url=TB_URL, language=LanguageOption.ENGLISH))


@pytest.fixture
def client(app):
    app.dependency_overrides[validate_auth_token] = _auth_info
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def store(app):
    return app.state.job_store


def _create(store, job_id: str, user_key: str) -> None:
    store.create(
        job_id,
        agent_key="coverage_checker",
        user_key=user_key,
        project_key="p",
        project_name="P",
        root_key=None,
        item_ids=["i1"],
        warnings=[],
    )


def _ticket(client, job_id: str, **params) -> dict:
    r = client.post(f"/jobs/{job_id}/view-ticket", params=params)
    assert r.status_code == 200, r.text
    return r.json()


# --- the store ------------------------------------------------------------


def test_ticket_opens_one_session_only():
    views = JobViewStore()
    ticket = views.issue_ticket("j1", "1", LanguageOption.ENGLISH)
    sid = views.redeem_ticket("j1", ticket)
    assert sid is not None
    assert views.redeem_ticket("j1", ticket) is None
    assert views.session("j1", sid).user_key == "1"


def test_ticket_expires():
    clock = _Clock()
    views = JobViewStore(ticket_ttl=timedelta(minutes=2), now=clock)
    ticket = views.issue_ticket("j1", "1", LanguageOption.ENGLISH)
    clock.moment += timedelta(minutes=3)
    assert views.redeem_ticket("j1", ticket) is None


def test_ticket_for_another_job_is_used_up():
    views = JobViewStore()
    ticket = views.issue_ticket("j1", "1", LanguageOption.ENGLISH)
    assert views.redeem_ticket("j2", ticket) is None
    assert views.redeem_ticket("j1", ticket) is None


def test_session_expires():
    clock = _Clock()
    views = JobViewStore(session_ttl=timedelta(hours=1), now=clock)
    sid = views.redeem_ticket("j1", views.issue_ticket("j1", "1", LanguageOption.ENGLISH))
    clock.moment += timedelta(hours=2)
    assert views.session("j1", sid) is None


def test_session_is_bound_to_its_job():
    views = JobViewStore()
    sid = views.redeem_ticket("j1", views.issue_ticket("j1", "1", LanguageOption.ENGLISH))
    assert views.session("j2", sid) is None
    assert views.session("j1", None) is None


# --- the ticket endpoint --------------------------------------------------


def test_ticket_for_own_job(client, store):
    _create(store, "j1", "1")
    body = _ticket(client, "j1")
    assert body["view_path"] == "/jobs/j1/view"
    assert body["view_token"]
    assert body["expires_in"] == 120


def test_no_ticket_for_foreign_or_unknown_job(client, store):
    _create(store, "j1", "2")
    assert client.post("/jobs/j1/view-ticket").status_code == 404
    assert client.post("/jobs/nope/view-ticket").status_code == 404


def test_ticket_requires_auth(app, store):
    _create(store, "j1", "1")
    with TestClient(app, raise_server_exceptions=False) as c:
        assert c.post("/jobs/j1/view-ticket").status_code == 401


# --- the page -------------------------------------------------------------


def test_ticket_opens_page_and_data(client, store):
    _create(store, "j1", "1")
    store.set_report("j1", "coverage_checker", {"aspects": [{"aspect": "a", "status": "covered"}]})
    ticket = _ticket(client, "j1")["view_token"]

    redirect = client.get("/jobs/j1/view", params={"view_token": ticket}, follow_redirects=False)
    assert redirect.status_code == 303
    assert redirect.headers["location"] == "/jobs/j1/view"
    set_cookie = redirect.headers["set-cookie"]
    assert f"{VIEW_COOKIE}=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "Path=/jobs/j1/view" in set_cookie

    page = client.get("/jobs/j1/view")
    assert page.status_code == 200
    assert page.headers["content-type"].startswith("text/html")
    csp = page.headers["content-security-policy"]
    assert "script-src 'self';" in csp
    assert "style-src 'self' 'nonce-" in csp
    assert "frame-ancestors 'none'" in csp
    assert page.headers["referrer-policy"] == "no-referrer"
    assert '<script type="application/json" id="job-view-config">' in page.text
    assert "/jobs/j1/view/data" in page.text
    assert "<!--job-view-config-->" not in page.text

    data = client.get("/jobs/j1/view/data")
    assert data.status_code == 200
    assert data.json()["report"]["aspects"][0]["status"] == "covered"
    assert data.headers["cache-control"] == "no-store"


def test_used_ticket_is_rejected(client, store):
    _create(store, "j1", "1")
    ticket = _ticket(client, "j1")["view_token"]
    client.get("/jobs/j1/view", params={"view_token": ticket}, follow_redirects=False)
    client.cookies.clear()
    again = client.get("/jobs/j1/view", params={"view_token": ticket}, follow_redirects=False)
    assert again.status_code == 401
    assert '"expired": true' in again.text


def test_page_and_data_require_a_session(client, store):
    _create(store, "j1", "1")
    assert client.get("/jobs/j1/view").status_code == 401
    assert client.get("/jobs/j1/view/data").status_code == 401


def test_session_of_one_job_does_not_open_another(client, store):
    _create(store, "j1", "1")
    _create(store, "j2", "1")
    ticket = _ticket(client, "j1")["view_token"]
    redirect = client.get("/jobs/j1/view", params={"view_token": ticket}, follow_redirects=False)
    sid = redirect.cookies[VIEW_COOKIE]
    client.cookies.clear()
    client.cookies.set(VIEW_COOKIE, sid)  # without a path, so it is sent for j2 too
    assert client.get("/jobs/j2/view/data").status_code == 401


def test_page_uses_requested_language(client, store):
    _create(store, "j1", "1")
    ticket = _ticket(client, "j1", language="de")["view_token"]
    page = client.get("/jobs/j1/view", params={"view_token": ticket})
    assert page.status_code == 200
    assert '<html lang="de">' in page.text
    assert '"language": "de"' in page.text


def test_page_without_frontend_build_says_so(client, store, built_page):
    (built_page / "job-view.html").unlink()
    _create(store, "j1", "1")
    ticket = _ticket(client, "j1")["view_token"]
    page = client.get("/jobs/j1/view", params={"view_token": ticket})
    assert page.status_code == 200
    assert "npm run build" in page.text


# --- the page's assets ---------------------------------------------------


def test_asset_is_served_with_its_type(client):
    r = client.get("/jobs/view-assets/assets/job-view-x1.js")
    assert r.status_code == 200
    assert r.text == "console.log(1)"
    assert r.headers["content-type"].startswith("text/javascript")
    assert "immutable" in r.headers["cache-control"]


def test_unknown_or_outside_asset_is_not_served(client, built_page):
    (built_page / "secret.txt").write_text("x", encoding="utf-8")
    assert client.get("/jobs/view-assets/assets/missing.js").status_code == 404
    assert client.get("/jobs/view-assets/assets/..%2Fsecret.txt").status_code == 404


def test_page_links_to_the_job_in_the_console(client, store):
    _create(store, "j1", "1")
    ticket = _ticket(client, "j1")["view_token"]
    page = client.get("/jobs/j1/view", params={"view_token": ticket})
    assert '"consoleUrl": "/admin/jobs/j1"' in page.text


def test_page_has_no_console_link_with_the_console_off(app, client, store):
    app.state.config.admin_ui.enabled = False
    _create(store, "j1", "1")
    ticket = _ticket(client, "j1")["view_token"]
    page = client.get("/jobs/j1/view", params={"view_token": ticket})
    assert page.status_code == 200
    assert "consoleUrl" not in page.text
