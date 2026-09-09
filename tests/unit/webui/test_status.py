from unittest.mock import MagicMock, patch

import requests

from testbench_ai_service.models.config import ProjectAgentConfig, ProjectConfig
from testbench_ai_service.models.language import LanguageOption
from testbench_ai_service.webui.status import agent_summary


def _status(client):
    return client.get("/admin/api/status")


def test_status_requires_a_session(client):
    assert _status(client).status_code == 401


def test_status_reports_service_facts(client, login):
    login()
    body = _status(client).json()
    assert body["service"]["host"] == "127.0.0.1"
    assert body["service"]["port"] == 8010
    assert body["service"]["version"]
    assert body["service"]["uptime_seconds"] >= 0


def test_status_reports_testbench_url_and_reachability(client, login):
    login()
    with patch("testbench_ai_service.webui.status.requests.get") as get:
        get.return_value = MagicMock(status_code=200)
        body = _status(client).json()
    assert body["testbench"]["url"].endswith("/api/")
    assert body["testbench"]["reachable"] is True


def test_unreachable_testbench_is_reported_not_raised(client, login):
    login()
    with patch(
        "testbench_ai_service.webui.status.requests.get",
        side_effect=requests.exceptions.ConnectionError("refused"),
    ):
        response = _status(client)
    assert response.status_code == 200
    assert response.json()["testbench"]["reachable"] is False


def test_api_keys_report_presence_only(client, login, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-super-secret-value")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    login()
    body = _status(client).json()
    keys = {entry["name"]: entry["present"] for entry in body["api_keys"]}
    assert keys["OPENAI_API_KEY"] is True
    assert keys["ANTHROPIC_API_KEY"] is False
    # The value must never appear anywhere in the payload.
    assert "sk-super-secret-value" not in str(body)


def test_agent_summary_counts_enabled_and_overrides(client, login):
    login()
    body = _status(client).json()
    assert body["agents"]["total"] == 3
    assert body["agents"]["enabled"] == 3
    assert body["agents"]["project_overrides"] == 0


def test_log_file_name_is_reported(client, login):
    login()
    assert _status(client).json()["log_file"] == "testbench-ai-service.log"


def test_agent_summary_counts_real_project_overrides(make_app):
    """Every other test exercises ``agent_summary`` with zero overrides, so the
    non-zero branch of ``project_overrides`` is otherwise unverified -- and the
    console's Status screen displays exactly this number. Pin the formula:

        project_overrides = sum(
            len(project.agents or {}) + (1 if project.language else 0)
            for project in config.projects.values()
        )

    proj1: a language override (+1) plus two per-agent overrides (+2) = 3
    proj2: two per-agent overrides, no language override (+0) = 2
    Total project_overrides = 3 + 2 = 5; projects = 2.
    """
    app = make_app(
        projects={
            "proj1": ProjectConfig(
                language=LanguageOption.GERMAN,
                agents={
                    "test_case_set_reviewer": ProjectAgentConfig(enabled=False),
                    "defect_explainer": ProjectAgentConfig(enabled=True),
                },
            ),
            "proj2": ProjectConfig(
                agents={
                    "test_case_set_reviewer": ProjectAgentConfig(enabled=True),
                    "test_case_set_describer": ProjectAgentConfig(enabled=False),
                },
            ),
        }
    )

    summary = agent_summary(app.state.config)

    assert summary.project_overrides == 5
    assert summary.projects == 2


def test_status_reports_zero_in_flight_tasks_on_a_quiet_service(client, login):
    login()

    body = client.get("/admin/api/status").json()

    assert body["in_flight_tasks"] == 0


def test_status_reports_a_tracked_task(app, client, login):
    login()
    registry = app.state.task_registry
    registry._labels.append("test_case_set_reviewer")
    try:
        body = client.get("/admin/api/status").json()
    finally:
        registry._labels.clear()

    assert body["in_flight_tasks"] == 1
