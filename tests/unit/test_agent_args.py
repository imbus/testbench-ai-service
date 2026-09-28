"""Tests for agent-specific ``args``: startup validation, project merge and injection."""

from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import Field, ValidationError

from testbench_ai_service.agents.requirement.agent import RequirementAgent
from testbench_ai_service.agents.requirement.model import RequirementAgentArgs
from testbench_ai_service.agents.routes import load_agent
from testbench_ai_service.config import DEFAULT_AGENTS, PROMPTS_DIR, AppConfig
from testbench_ai_service.models.agent import AgentArgs
from testbench_ai_service.models.config import (
    AgentConfig,
    ProjectAgentConfig,
    ProjectConfig,
    PromptConfig,
    merge_agent_args,
)
from testbench_ai_service.utils.config import get_agent_config

REQUIREMENT_CLASS_PATH = "testbench_ai_service.agents.requirement.agent.RequirementAgent"


class _ArgsWithRequired(AgentArgs):
    output_field: str
    max_items: int = Field(10, gt=0)


def _requirement_agent(args: dict | None = None) -> AgentConfig:
    return AgentConfig(
        enabled=True,
        endpoint_path="/requirement-test-ideas",
        class_path=REQUIREMENT_CLASS_PATH,
        prompt=PromptConfig(file=Path("requirement/prompt.yaml")),
        args=args or {},
    )


def _make_app_config(args: dict | None = None, project_args: dict | None = None) -> AppConfig:
    projects = {}
    if project_args is not None:
        projects["P1"] = ProjectConfig(
            agents={"requirement": ProjectAgentConfig(args=project_args)}
        )
    with (
        patch("testbench_ai_service.config.validate_tb_server_url"),
        patch(
            "testbench_ai_service.config.AppConfig.validate_prompts_dir_exists",
            return_value=PROMPTS_DIR,
        ),
    ):
        return AppConfig(
            agents={**DEFAULT_AGENTS, "requirement": _requirement_agent(args)},
            projects=projects,
        )


def _error_locs(error: ValidationError) -> list[tuple]:
    return [detail["loc"] for detail in error.errors()]


@pytest.fixture
def required_args(monkeypatch):
    """Give the requirement agent an args model with a required field."""
    monkeypatch.setattr(RequirementAgent, "ARGS_CLASS", _ArgsWithRequired)


class TestStartupValidation:
    def test_agents_without_args_need_no_table(self):
        config = _make_app_config()

        assert config.agents["requirement"].args == {}
        assert config.agents["defect_explainer"].args == {}

    def test_optional_arg_is_accepted(self):
        config = _make_app_config(args={"max_requirements": 20})

        assert config.agents["requirement"].args == {"max_requirements": 20}

    def test_unknown_arg_is_rejected(self):
        with pytest.raises(ValidationError) as exc:
            _make_app_config(args={"max_requirement": 20})

        assert ("agents", "requirement", "args", "max_requirement") in _error_locs(exc.value)

    def test_arg_constraint_is_enforced(self):
        with pytest.raises(ValidationError) as exc:
            _make_app_config(args={"max_requirements": 0})

        assert ("agents", "requirement", "args", "max_requirements") in _error_locs(exc.value)

    def test_rm_service_url_without_credentials_is_rejected(self):
        with pytest.raises(ValidationError, match="requires rm_username and rm_password"):
            _make_app_config(args={"rm_service_url": "http://rm"})

    def test_missing_required_arg_is_rejected(self, required_args):
        with pytest.raises(ValidationError) as exc:
            _make_app_config()

        assert ("agents", "requirement", "args", "output_field") in _error_locs(exc.value)

    def test_every_error_is_reported_at_once(self, required_args):
        with pytest.raises(ValidationError) as exc:
            _make_app_config(args={"max_items": 0, "typo": 1})

        assert set(_error_locs(exc.value)) == {
            ("agents", "requirement", "args", "output_field"),
            ("agents", "requirement", "args", "max_items"),
            ("agents", "requirement", "args", "typo"),
        }

    def test_required_arg_must_be_set_globally_not_only_per_project(self, required_args):
        with pytest.raises(ValidationError) as exc:
            _make_app_config(project_args={"output_field": "description"})

        assert ("agents", "requirement", "args", "output_field") in _error_locs(exc.value)

    def test_invalid_project_override_is_rejected_with_its_location(self):
        with pytest.raises(ValidationError) as exc:
            _make_app_config(project_args={"max_requirements": -1})

        assert ("projects", "P1", "agents", "requirement", "args", "max_requirements") in (
            _error_locs(exc.value)
        )


class TestProjectMerge:
    def test_merge_overrides_single_keys(self):
        assert merge_agent_args({"a": 1, "b": 2}, {"b": 3}) == {"a": 1, "b": 3}

    def test_merge_without_project_args_keeps_global(self):
        assert merge_agent_args({"a": 1}, None) == {"a": 1}

    def test_project_override_keeps_the_other_global_args(self, required_args):
        config = _make_app_config(
            args={"output_field": "description", "max_items": 5},
            project_args={"max_items": 2},
        )

        agent_config = get_agent_config("requirement", config, "P1")

        assert agent_config.args == {"output_field": "description", "max_items": 2}

    def test_project_without_args_override_uses_global_args(self):
        config = _make_app_config(args={"max_requirements": 20})
        config.projects["P2"] = ProjectConfig(
            agents={"requirement": ProjectAgentConfig(enabled=False)}
        )

        agent_config = get_agent_config("requirement", config, "P2")

        assert agent_config.args == {"max_requirements": 20}
        assert agent_config.enabled is False


class TestLoadAgent:
    def test_agent_receives_its_validated_args(self):
        agent = load_agent(_requirement_agent({"max_requirements": 20}))

        assert isinstance(agent.args, RequirementAgentArgs)
        assert agent.args.max_requirements == 20

    def test_agent_without_args_table_gets_the_defaults(self):
        agent = load_agent(_requirement_agent())

        assert agent.args == RequirementAgentArgs()

    def test_agent_constructed_directly_gets_the_defaults(self):
        assert RequirementAgent().args.max_requirements is None
