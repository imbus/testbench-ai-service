from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from testbench_ai_service.agents.coverage_checker.agent import CoverageChecker
from testbench_ai_service.agents.routes import get_agent_routers, load_agent
from testbench_ai_service.config import DEFAULT_AGENTS, PROMPTS_DIR, AppConfig
from testbench_ai_service.models.config import AgentConfig, PromptConfig

CHECKER = AgentConfig(
    enabled=True,
    endpoint_path="/coverage",
    class_path="testbench_ai_service.agents.coverage_checker.agent.CoverageChecker",
    prompt=PromptConfig(file=Path("coverage_checker/prompt.yaml")),
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
    assert "coverage_checker" not in DEFAULT_AGENTS


def test_config_with_the_checker_validates_and_gets_a_route():
    config = _app_config({**DEFAULT_AGENTS, "coverage_checker": CHECKER})

    paths = {route.path for router in get_agent_routers(config) for route in router.routes}

    assert "/coverage" in paths


def test_invalid_args_are_rejected_at_startup():
    bad = CHECKER.model_copy(update={"args": {"max_aspects": 0}})

    with pytest.raises(ValidationError):
        _app_config({**DEFAULT_AGENTS, "coverage_checker": bad})


def test_load_agent_passes_the_args():
    agent = load_agent(CHECKER.model_copy(update={"args": {"max_aspects": 5}}))

    assert isinstance(agent, CoverageChecker)
    assert agent.args.max_aspects == 5
