import asyncio
from unittest.mock import MagicMock, patch

import requests

from testbench_ai_service.agent_packages import loaded
from testbench_ai_service.agent_packages.manifest import site_dir
from testbench_ai_service.config import DEFAULT_AGENTS
from testbench_ai_service.llm.base import TokenUsage
from testbench_ai_service.models.config import (
    AgentConfig,
    ProjectAgentConfig,
    ProjectConfig,
    PromptConfig,
)
from testbench_ai_service.models.language import LanguageOption
from testbench_ai_service.usage import UsageStore
from testbench_ai_service.webui.status import agent_summary
from tests.helpers.packages import CLASS_PATH, PACKAGE, install_package


def test_status_lists_unloaded_package_agent(make_app, tmp_path):
    packages_dir = tmp_path / "packages"
    install_package(packages_dir)
    prompt = site_dir(packages_dir, PACKAGE, "1.0.0") / "acme/rater/prompts/en/prompt.yaml"
    agent = AgentConfig(
        enabled=True,
        endpoint_path="/acme",
        class_path=CLASS_PATH,
        prompt=PromptConfig(file=prompt),
        package=PACKAGE,
    )
    app = make_app(agents={**DEFAULT_AGENTS, "acme": agent}, agent_packages={"dir": packages_dir})
    loaded.mark_failed("broken-pkg", "cannot import 'broken.Agent'")

    summary = agent_summary(app.state.config)

    assert set(summary.unloaded_packages) == {PACKAGE, "broken-pkg"}
    assert summary.unloaded_packages["broken-pkg"] == "cannot import 'broken.Agent'"
    assert "restart" in summary.unloaded_packages[PACKAGE].lower()


def test_status_lists_no_loaded_package(make_app):
    summary = agent_summary(make_app().state.config)
    assert summary.unloaded_packages == {}
    assert summary.failed_agents == {}


def test_status_says_a_package_missing_from_the_manifest_is_missing(make_app, tmp_path):
    agent = AgentConfig(
        enabled=True,
        endpoint_path="/acme",
        class_path=CLASS_PATH,
        prompt=PromptConfig(file="test_case_set_reviewer/prompt.yaml"),
        package="gone-pkg",
    )
    app = make_app(
        agents={**DEFAULT_AGENTS, "acme": agent}, agent_packages={"dir": tmp_path / "packages"}
    )

    summary = agent_summary(app.state.config)

    assert "missing" in summary.unloaded_packages["gone-pkg"]


def test_status_lists_agents_that_failed_at_startup(make_app):
    loaded.mark_agent_failed("acme_broken", "cannot import 'acme.broken.BrokenAgent'")

    summary = agent_summary(make_app().state.config)

    assert summary.failed_agents == {"acme_broken": "cannot import 'acme.broken.BrokenAgent'"}


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


def test_testbench_probe_runs_off_the_event_loop(client, login):
    """A slow TestBench must not stall every other request while /status waits."""
    login()
    probed_on_loop: list[bool] = []

    def fake_get(*_args, **_kwargs):
        try:
            asyncio.get_running_loop()
            probed_on_loop.append(True)
        except RuntimeError:
            probed_on_loop.append(False)
        return MagicMock(status_code=200)

    with patch("testbench_ai_service.webui.status.requests.get", side_effect=fake_get):
        _status(client)

    assert probed_on_loop == [False]


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


def test_status_includes_restart_required_defaulting_to_empty(client, login):
    login()

    body = client.get("/admin/api/status").json()

    assert "restart_required" in body
    assert body["restart_required"] == []


def test_status_reports_no_token_usage_on_a_fresh_service(client, login):
    login()

    body = client.get("/admin/api/status").json()

    assert body["token_usage"] == {"available": True, "models": []}


def test_status_reports_the_token_usage_per_model(app, client, login):
    login()
    app.state.usage_store.record("anthropic", "claude-opus-5", TokenUsage(800, 300, 100))
    app.state.usage_store.record("anthropic", "claude-opus-5", TokenUsage(200, 100))

    [entry] = client.get("/admin/api/status").json()["token_usage"]["models"]

    assert entry["provider"] == "anthropic"
    assert entry["model"] == "claude-opus-5"
    assert (entry["calls"], entry["input_tokens"], entry["output_tokens"]) == (2, 1000, 400)
    assert entry["reasoning_tokens"] == 100
    assert entry["last_used"]


def test_an_unreadable_usage_file_is_reported_not_raised(app, client, login):
    login()
    app.state.usage_store = UsageStore(app.state.usage_store.path.parent)  # a directory

    response = client.get("/admin/api/status")

    assert response.status_code == 200
    assert response.json()["token_usage"] == {"available": False, "models": []}
