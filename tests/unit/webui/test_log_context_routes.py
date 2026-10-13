from unittest.mock import patch

from testbench_ai_service.log import logger as service_logger


def _csrf(client):
    return {"X-CSRF-Token": client.cookies.get("tbai_admin_csrf")}


def test_projects_refresh_records_carry_the_user(client, login, capture):
    login()
    capture.records.clear()
    with (
        patch(
            "testbench_ai_service.webui.routes.fetch_projects_with_token",
            side_effect=lambda *a, **k: service_logger.info("refreshing") or [],
        ),
        patch("testbench_ai_service.webui.routes.record_projects"),
    ):
        client.post("/admin/api/projects/refresh", headers=_csrf(client))
    refreshing = [r for r in capture.records if r.getMessage() == "refreshing"]
    assert refreshing
    assert refreshing[0].scope == "user"
    assert refreshing[0].user_key == "u-1"
    assert refreshing[0].username == "a.mueller"


def test_a_read_route_without_bind_log_user_stays_request_scoped(client, login, capture):
    login()
    capture.records.clear()
    with patch(
        "testbench_ai_service.webui.routes.projects_response",
        side_effect=lambda s: service_logger.info("reading") or {"projects": []},
    ):
        client.get("/admin/api/projects")
    reading = [r for r in capture.records if r.getMessage() == "reading"]
    assert reading
    assert reading[0].scope == "request"
