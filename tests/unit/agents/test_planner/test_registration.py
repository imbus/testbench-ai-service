from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from testbench_ai_service.agents.routes import get_agent_routers, load_agent
from testbench_ai_service.agents.test_planner.agent import TestPlannerAgent
from testbench_ai_service.config import DEFAULT_AGENTS, PROMPTS_DIR, AppConfig
from testbench_ai_service.models.config import AgentConfig, PromptConfig

PLANNER = AgentConfig(
    enabled=True,
    endpoint_path="/test-planner",
    class_path="testbench_ai_service.agents.test_planner.agent.TestPlannerAgent",
    prompt=PromptConfig(file=Path("test_planner/prompt.yaml")),
)


def _app_config(agents):
    with (
        patch("testbench_ai_service.config.validate_tb_server_url"),
        patch(
            "testbench_ai_service.config.AppConfig.validate_prompts_dir_exists",
            return_value=PROMPTS_DIR,
        ),
    ):
        return AppConfig(agents=agents)


def test_not_part_of_the_default_agents():
    assert "test_planner" not in DEFAULT_AGENTS


def test_config_with_the_planner_validates_and_gets_a_route():
    config = _app_config({**DEFAULT_AGENTS, "test_planner": PLANNER})

    paths = {route.path for router in get_agent_routers(config) for route in router.routes}

    assert "/test-planner" in paths


def test_config_without_the_planner_is_unchanged():
    config = _app_config(DEFAULT_AGENTS)

    paths = {route.path for router in get_agent_routers(config) for route in router.routes}

    assert "/test-planner" not in paths


def test_invalid_planner_args_are_rejected_at_startup():
    bad = PLANNER.model_copy(update={"args": {"cluster_threshold": 2}})

    with pytest.raises(ValidationError):
        _app_config({**DEFAULT_AGENTS, "test_planner": bad})


def test_load_agent_passes_the_args():
    agent = load_agent(
        PLANNER.model_copy(update={"args": {"mandatory_tag": "must", "embedding": {"model": "m"}}})
    )

    assert isinstance(agent, TestPlannerAgent)
    assert agent.args.mandatory_tag == "must"
    assert agent.args.embedding.model == "m"
