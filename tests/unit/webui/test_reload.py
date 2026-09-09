from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from testbench_ai_service.config import AppConfig
from testbench_ai_service.models.config import AgentConfig, PromptConfig
from testbench_ai_service.webui.reload import hot_reload, restart_required

TB_URL = "https://localhost:9443/api/"


@pytest.fixture(autouse=True)
def no_url_probe():
    with (
        patch("testbench_ai_service.config.validate_tb_server_url"),
        # restart_required compares field values and never touches template
        # variables, so the agent-data compatibility check is irrelevant here;
        # it is disabled only so the fixtures can pair an arbitrary class_path
        # with a fixed prompt file in order to test that a class_path change
        # is detected.
        patch("testbench_ai_service.config.validate_agent_variable", return_value=True),
    ):
        yield


def make_config(**kwargs) -> AppConfig:
    return AppConfig(tb_server_url=TB_URL, **kwargs)


def agent(endpoint_path="/reviews", class_path=None, enabled=True) -> AgentConfig:
    return AgentConfig(
        enabled=enabled,
        endpoint_path=endpoint_path,
        class_path=class_path
        or "testbench_ai_service.agents.test_case_set_reviewer.agent.TestCaseSetReviewer",
        prompt=PromptConfig(file=Path("test_case_set_reviewer/prompt.yaml")),
    )


def test_an_unchanged_config_needs_no_restart():
    assert restart_required(make_config(), make_config()) == []


def test_a_hot_swappable_change_needs_no_restart():
    """language, llm_config and logging are all re-applied in process."""
    old = make_config(language="de")
    new = make_config(language="en")

    assert restart_required(old, new) == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("host", "0.0.0.0"),
        ("port", 9999),
        ("trusted_proxies", ["10.0.0.1"]),
    ],
)
def test_a_boot_fixed_field_needs_a_restart(field: str, value):
    new = make_config(**{field: value})

    assert restart_required(make_config(), new) == [field]


def test_a_tls_change_needs_a_restart(tmp_path: Path):
    """ssl_cert/ssl_key/ssl_ca_cert are handed to uvicorn at boot."""
    cert = tmp_path / "cert.pem"
    cert.write_text("x", encoding="utf-8")

    new = make_config(ssl_cert=str(cert))

    assert restart_required(make_config(), new) == ["ssl_cert"]


def test_several_boot_fixed_changes_are_all_reported_and_sorted():
    new = make_config(host="0.0.0.0", port=9999)

    assert restart_required(make_config(), new) == ["host", "port"]


def test_a_changed_agent_endpoint_path_needs_a_restart():
    """init_routers registers the agent routers once, at startup."""
    old = make_config(agents={"reviewer": agent(endpoint_path="/a")})
    new = make_config(agents={"reviewer": agent(endpoint_path="/b")})

    assert restart_required(old, new) == ["agents.reviewer.endpoint_path"]


def test_a_changed_agent_class_path_needs_a_restart():
    old = make_config(agents={"reviewer": agent()})
    new = make_config(
        agents={
            "reviewer": agent(
                class_path="testbench_ai_service.agents.defect_explainer.agent.DefectExplainer"
            )
        }
    )

    assert restart_required(old, new) == ["agents.reviewer.class_path"]


def test_toggling_an_agent_enabled_flag_does_not_need_a_restart():
    """The router exists either way; 'enabled' is checked per request."""
    old = make_config(agents={"reviewer": agent(enabled=True)})
    new = make_config(agents={"reviewer": agent(enabled=False)})

    assert restart_required(old, new) == []


def test_a_new_agent_needs_a_restart():
    old = make_config(agents={"reviewer": agent()})
    new = make_config(
        agents={
            "reviewer": agent(),
            "explainer": AgentConfig(
                enabled=True,
                endpoint_path="/defect-explanations",
                class_path="testbench_ai_service.agents.defect_explainer.agent.DefectExplainer",
                prompt=PromptConfig(file=Path("defect_explainer/prompt.yaml")),
            ),
        }
    )

    assert restart_required(old, new) == ["agents.explainer"]


def test_a_removed_agent_needs_a_restart():
    old = make_config(agents={"reviewer": agent()})
    new = make_config(agents={})

    assert restart_required(old, new) == ["agents.reviewer"]


def test_changing_an_agent_prompt_file_does_not_need_a_restart():
    """The prompt is resolved per request, not baked into the router."""
    old = make_config(agents={"reviewer": agent()})
    changed = agent()
    changed.prompt = PromptConfig(file=Path("test_case_set_reviewer/prompt.yaml"), variant="quick")
    new = make_config(agents={"reviewer": changed})

    assert restart_required(old, new) == []


def test_admin_ui_enabled_change_needs_a_restart():
    """init_webui() is called once from create_app(); toggling the console requires restart."""
    old = make_config()
    new = make_config(admin_ui={"enabled": False})

    assert restart_required(old, new) == ["admin_ui.enabled"]


def test_admin_ui_require_loopback_change_does_not_need_a_restart():
    """require_loopback is read per request through get_app_config and is hot-swappable."""
    old = make_config()
    new = make_config(admin_ui={"require_loopback": True})

    assert restart_required(old, new) == []


def test_port_and_admin_ui_enabled_changes_are_sorted():
    """Multiple restart-required changes are returned sorted."""
    new = make_config(port=9999, admin_ui={"enabled": False})

    assert restart_required(make_config(), new) == ["admin_ui.enabled", "port"]


def fake_app(config: AppConfig):
    """A stand-in for the FastAPI app: reload only touches app.state."""
    app = MagicMock()
    app.state.config = config
    app.state.llm_factory = MagicMock()
    app.state.llm_factory.close_clients = AsyncMock()
    app.state.llm_factory.init_clients = MagicMock()
    return app


class TestHotReload:
    """hot_reload's disk- and network-touching collaborators are replaced for
    every test here.

    A real ``setup_logging()`` would append to the repository's own log file
    and, via ``disable_existing_loggers``, can silently disable pytest's own
    logging for the rest of the session -- see the task-10 correction. A real
    ``LLMFactory()`` would try to resolve a provider credential from the
    environment; patching it is also what gives the assertions below
    (``init_clients.assert_called_once()``, ``call_args``) a Mock to inspect,
    since ``hot_reload`` always constructs a *new* factory rather than reusing
    ``app.state.llm_factory``.
    """

    @pytest.fixture(autouse=True)
    def _patched_collaborators(self, monkeypatch):
        monkeypatch.setattr("testbench_ai_service.webui.reload.setup_logging", MagicMock())
        monkeypatch.setattr("testbench_ai_service.webui.reload.load_translations", MagicMock())

        new_factory = MagicMock()
        new_factory.init_clients = MagicMock()
        new_factory.close_clients = AsyncMock()
        monkeypatch.setattr(
            "testbench_ai_service.webui.reload.LLMFactory", MagicMock(return_value=new_factory)
        )

    async def test_hot_reload_swaps_the_config_on_app_state(self):
        app = fake_app(make_config(language="de"))
        new = make_config(language="en")

        await hot_reload(app, new)

        assert app.state.config is new

    async def test_hot_reload_closes_the_old_llm_clients_before_building_new_ones(self):
        app = fake_app(make_config())
        old_factory = app.state.llm_factory

        await hot_reload(app, make_config())

        old_factory.close_clients.assert_awaited_once()
        assert app.state.llm_factory is not old_factory
        app.state.llm_factory.init_clients.assert_called_once()

    async def test_hot_reload_initialises_the_new_clients_from_the_new_llm_config(self):
        app = fake_app(make_config())
        new = make_config()
        new.llm_config.model = "gpt-4.1"

        await hot_reload(app, new)

        (configs,), _ = app.state.llm_factory.init_clients.call_args
        assert configs == [new.llm_config]

    async def test_hot_reload_reapplies_logging_and_translations(self, monkeypatch):
        calls: list[str] = []
        monkeypatch.setattr(
            "testbench_ai_service.webui.reload.setup_logging",
            lambda _config: calls.append("logging"),
        )
        monkeypatch.setattr(
            "testbench_ai_service.webui.reload.load_translations",
            lambda: calls.append("translations"),
        )
        app = fake_app(make_config())

        await hot_reload(app, make_config())

        assert calls == ["logging", "translations"]

    async def test_a_failure_closing_the_old_clients_does_not_abort_the_reload(self):
        """The file is already written; refusing to swap would leave disk and
        memory disagreeing with nothing to fix it. The degraded close is still
        reported through the return value."""
        app = fake_app(make_config())
        app.state.llm_factory.close_clients = AsyncMock(side_effect=RuntimeError("already closed"))
        new = make_config(language="en")

        result = await hot_reload(app, new)

        assert result is False
        assert app.state.config is new
        app.state.llm_factory.init_clients.assert_called_once()

    async def test_a_fully_successful_reload_returns_true(self):
        app = fake_app(make_config())

        result = await hot_reload(app, make_config())

        assert result is True

    async def test_a_failure_pre_warming_the_new_clients_does_not_corrupt_state(self, monkeypatch):
        """Regression guard: switching the LLM provider without a matching
        credential in the environment must not leave the process holding the
        new config together with the old, already-closed factory. The new
        (only partially warmed) factory is still installed -- its clients are
        created lazily on demand, so the missing credential surfaces on the
        next agent request instead of corrupting the reload."""
        broken_factory = MagicMock()
        broken_factory.init_clients = MagicMock(side_effect=ValueError("no API key"))
        monkeypatch.setattr(
            "testbench_ai_service.webui.reload.LLMFactory",
            MagicMock(return_value=broken_factory),
        )
        app = fake_app(make_config())
        old_factory = app.state.llm_factory
        new = make_config(language="en")

        result = await hot_reload(app, new)

        assert result is False
        assert app.state.config is new
        assert app.state.llm_factory is broken_factory
        assert app.state.llm_factory is not old_factory
