from pathlib import Path
from unittest.mock import patch

import pytest

from testbench_ai_service.config import AppConfig
from testbench_ai_service.models.config import AgentConfig, PromptConfig
from testbench_ai_service.webui.reload import restart_required

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
