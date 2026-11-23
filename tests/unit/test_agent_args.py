"""Tests for agent-specific ``args``: startup validation, project merge and injection."""

from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import Field, ValidationError

from testbench_ai_service.agents.routes import load_agent
from testbench_ai_service.agents.test_case_set_reviewer.agent import TestCaseSetReviewer
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

AGENT_KEY = "test_case_set_reviewer"
REVIEWER_CLASS_PATH = "testbench_ai_service.agents.test_case_set_reviewer.agent.TestCaseSetReviewer"


class _OptionalArgs(AgentArgs):
    max_items: int | None = Field(None, gt=0)


class _ArgsWithRequired(AgentArgs):
    output_field: str
    max_items: int = Field(10, gt=0)


@pytest.fixture(autouse=True)
def optional_args(monkeypatch):
    """Give the reviewer an args model with one optional field."""
    monkeypatch.setattr(TestCaseSetReviewer, "ARGS_CLASS", _OptionalArgs)


@pytest.fixture
def required_args(monkeypatch):
    """Give the reviewer an args model with a required field."""
    monkeypatch.setattr(TestCaseSetReviewer, "ARGS_CLASS", _ArgsWithRequired)


def _reviewer_agent(args: dict | None = None) -> AgentConfig:
    return AgentConfig(
        enabled=True,
        endpoint_path="/test-case-set-reviews",
        class_path=REVIEWER_CLASS_PATH,
        prompt=PromptConfig(file=Path("test_case_set_reviewer/prompt.yaml")),
        args=args or {},
    )


def _make_app_config(args: dict | None = None, project_args: dict | None = None) -> AppConfig:
    projects = {}
    if project_args is not None:
        projects["P1"] = ProjectConfig(agents={AGENT_KEY: ProjectAgentConfig(args=project_args)})
    with (
        patch("testbench_ai_service.config.validate_tb_server_url"),
        patch(
            "testbench_ai_service.config.AppConfig.validate_prompts_dir_exists",
            return_value=PROMPTS_DIR,
        ),
    ):
        return AppConfig(
            agents={**DEFAULT_AGENTS, AGENT_KEY: _reviewer_agent(args)},
            projects=projects,
        )


def _error_locs(error: ValidationError) -> list[tuple]:
    return [detail["loc"] for detail in error.errors()]


class TestStartupValidation:
    def test_agents_without_args_need_no_table(self):
        config = _make_app_config()

        assert config.agents[AGENT_KEY].args == {}
        assert config.agents["defect_explainer"].args == {}

    def test_optional_arg_is_accepted(self):
        config = _make_app_config(args={"max_items": 20})

        assert config.agents[AGENT_KEY].args == {"max_items": 20}

    def test_unknown_arg_is_rejected(self):
        with pytest.raises(ValidationError) as exc:
            _make_app_config(args={"max_item": 20})

        assert ("agents", AGENT_KEY, "args", "max_item") in _error_locs(exc.value)

    def test_arg_constraint_is_enforced(self):
        with pytest.raises(ValidationError) as exc:
            _make_app_config(args={"max_items": 0})

        assert ("agents", AGENT_KEY, "args", "max_items") in _error_locs(exc.value)

    def test_missing_required_arg_is_rejected(self, required_args):
        with pytest.raises(ValidationError) as exc:
            _make_app_config()

        assert ("agents", AGENT_KEY, "args", "output_field") in _error_locs(exc.value)

    def test_every_error_is_reported_at_once(self, required_args):
        with pytest.raises(ValidationError) as exc:
            _make_app_config(args={"max_items": 0, "typo": 1})

        assert set(_error_locs(exc.value)) == {
            ("agents", AGENT_KEY, "args", "output_field"),
            ("agents", AGENT_KEY, "args", "max_items"),
            ("agents", AGENT_KEY, "args", "typo"),
        }

    def test_required_arg_must_be_set_globally_not_only_per_project(self, required_args):
        with pytest.raises(ValidationError) as exc:
            _make_app_config(project_args={"output_field": "description"})

        assert ("agents", AGENT_KEY, "args", "output_field") in _error_locs(exc.value)

    def test_invalid_project_override_is_rejected_with_its_location(self):
        with pytest.raises(ValidationError) as exc:
            _make_app_config(project_args={"max_items": -1})

        assert ("projects", "P1", "agents", AGENT_KEY, "args", "max_items") in _error_locs(
            exc.value
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

        agent_config = get_agent_config(AGENT_KEY, config, "P1")

        assert agent_config.args == {"output_field": "description", "max_items": 2}

    def test_project_without_args_override_uses_global_args(self):
        config = _make_app_config(args={"max_items": 20})
        config.projects["P2"] = ProjectConfig(agents={AGENT_KEY: ProjectAgentConfig(enabled=False)})

        agent_config = get_agent_config(AGENT_KEY, config, "P2")

        assert agent_config.args == {"max_items": 20}
        assert agent_config.enabled is False


class TestLoadAgent:
    def test_agent_receives_its_validated_args(self):
        agent = load_agent(_reviewer_agent({"max_items": 20}))

        assert isinstance(agent.args, _OptionalArgs)
        assert agent.args.max_items == 20

    def test_agent_without_args_table_gets_the_defaults(self):
        agent = load_agent(_reviewer_agent())

        assert agent.args == _OptionalArgs()

    def test_agent_constructed_directly_gets_the_defaults(self):
        assert TestCaseSetReviewer().args.max_items is None


class _LegacyAgent(TestCaseSetReviewer):
    """A custom agent written before args existed: own __init__, no parameters."""

    def __init__(self):
        self.initialised = True


class _AgentWithOwnArgs(TestCaseSetReviewer):
    """A custom agent that already used ``self.args`` for something else."""

    ARGS_CLASS = AgentArgs

    def __init__(self):
        self.args = ["--own", "value"]


class _AgentWithReadOnlyArgs(TestCaseSetReviewer):
    ARGS_CLASS = AgentArgs

    def __init__(self):
        pass

    @property
    def args(self):
        return "fixed"


class TestBackwardCompatibility:
    def test_custom_agent_with_own_no_arg_init_still_loads(self):
        config = _reviewer_agent({"max_items": 3}).model_copy(
            update={"class_path": f"{__name__}._LegacyAgent"}
        )

        agent = load_agent(config)

        assert agent.initialised
        assert agent.args.max_items == 3

    def test_default_agents_are_unchanged(self):
        assert set(DEFAULT_AGENTS) == {
            "test_case_set_reviewer",
            "test_case_set_describer",
            "defect_explainer",
        }
        assert all(agent.args == {} for agent in DEFAULT_AGENTS.values())

    def test_own_args_attribute_is_kept_without_an_args_table(self):
        config = _reviewer_agent().model_copy(
            update={"class_path": f"{__name__}._AgentWithOwnArgs"}
        )

        assert load_agent(config).args == ["--own", "value"]

    def test_read_only_args_property_still_loads(self):
        config = _reviewer_agent().model_copy(
            update={"class_path": f"{__name__}._AgentWithReadOnlyArgs"}
        )

        assert load_agent(config).args == "fixed"
