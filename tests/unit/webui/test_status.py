from unittest.mock import MagicMock, patch

import requests


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
