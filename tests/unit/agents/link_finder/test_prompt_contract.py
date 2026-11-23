"""The shipped prompts fit the agent: every step exists, uses only declared variables,
matches the schema and renders. The shared steps stay copies of the coverage checker's."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from testbench_ai_service.agents.link_finder.agent import LinkFinder
from testbench_ai_service.agents.routes import validate_template_and_agent_vars
from testbench_ai_service.models.config import PromptConfig
from testbench_ai_service.utils.build_prompt_utils import build_prompt
from testbench_ai_service.validators import validate_yaml_to_schema

PROMPTS = Path(__file__).parents[4] / "testbench_ai_service" / "prompts"

SAMPLES = {
    "aspects": {"requirement": "REQ-42: Login", "max_aspects": "12"},
    "prefilter": {
        "requirement": "REQ-42: Login",
        "aspects": "A1 [happy_path] Login succeeds",
        "test_case_sets": "iTB-TC-1 | /Auth/Login | Login | Checks the login",
    },
    "interpretation": {
        "requirement": "REQ-42: Login",
        "aspects": "A1 [happy_path] Login succeeds",
        "test_case_set": "Login (/Auth/Login)",
        "test_cases": "Test case TC-1",
    },
}

SHARED_FILES = {
    "en": ["aspects_system.jinja", "aspects_user.jinja"],
    "de": ["aspekte_system.jinja", "aspekte_user.jinja"],
}
INTERPRETATION_FILES = ["interpretation_system.jinja", "interpretation_user.jinja"]


def _prompt(language: str) -> Path:
    return PROMPTS / language / "link_finder" / "prompt.yaml"


@pytest.mark.parametrize("language", ["en", "de"])
def test_every_template_variable_is_declared_by_the_agent(language):
    context = SimpleNamespace(prompt_config=SimpleNamespace(file=_prompt(language), variant=None))

    validate_template_and_agent_vars(context, LinkFinder())


@pytest.mark.parametrize("language", ["en", "de"])
def test_the_prompt_matches_the_schema(language):
    assert validate_yaml_to_schema(_prompt(language)) == _prompt(language)


@pytest.mark.parametrize("language", ["en", "de"])
@pytest.mark.parametrize("step", list(SAMPLES))
def test_each_step_renders_a_system_and_a_user_message(language, step):
    prompt = build_prompt(PromptConfig(file=_prompt(language)), SAMPLES[step], step=step)

    assert [message.role for message in prompt.messages] == ["system", "user"]
    assert all(message.content for message in prompt.messages)
    assert "REQ-42: Login" in prompt.messages[1].content


@pytest.mark.parametrize("language", ["en", "de"])
def test_the_steps_match_the_agent(language):
    prompt = _prompt(language).read_text(encoding="utf-8")

    for step in LinkFinder.STEP_DATA_CLASSES:
        assert f"      {step}:" in prompt


@pytest.mark.parametrize("language", ["en", "de"])
def test_the_shared_steps_are_copies_of_the_coverage_checker(language):
    for name in SHARED_FILES[language] + INTERPRETATION_FILES:
        own = (PROMPTS / language / "link_finder" / name).read_text(encoding="utf-8")
        coverage = (PROMPTS / language / "coverage_checker" / name).read_text(encoding="utf-8")
        assert own == coverage, name
