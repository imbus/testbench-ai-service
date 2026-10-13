"""Building the prompt of one step of a multi-step variant."""

from typing import TypedDict

import pytest

from testbench_ai_service.models.config import PromptConfig
from testbench_ai_service.utils.build_prompt_utils import build_prompt
from testbench_ai_service.utils.prompt_utils import step_agent_variable_errors, template_variables

PROMPT = """\
name: "x"
default_model: "m"
default_variant: "A"
variants:
  - name: "A"
    messages: []
    steps:
      aspects:
        - role: "system"
          text: "Split {{ agent.requirement }}"
      gaps:
        - role: "user"
          file: "gaps_user.jinja"
"""


@pytest.fixture
def prompt_file(tmp_path):
    path = tmp_path / "prompt.yaml"
    path.write_text(PROMPT, encoding="utf-8")
    (tmp_path / "gaps_user.jinja").write_text("Gaps of {{ agent.gaps }}", encoding="utf-8")
    return path


def test_a_step_renders_its_own_messages(prompt_file):
    prompt = build_prompt(PromptConfig(file=prompt_file), {"requirement": "REQ-1"}, step="aspects")

    assert [(m.role, m.content) for m in prompt.messages] == [("system", "Split REQ-1")]


def test_a_step_reads_its_template_files_beside_the_prompt(prompt_file):
    prompt = build_prompt(PromptConfig(file=prompt_file), {"gaps": "A2"}, step="gaps")

    assert prompt.messages[0].content == "Gaps of A2"


def test_without_a_step_the_empty_messages_render_nothing(prompt_file):
    assert build_prompt(PromptConfig(file=prompt_file)).messages == []


def test_an_unknown_step_raises(prompt_file):
    with pytest.raises(ValueError, match="Step 'nope' not found"):
        build_prompt(PromptConfig(file=prompt_file), step="nope")


def test_template_variables_are_collected_per_step(prompt_file):
    assert template_variables(prompt_file, step="aspects") == {"agent.requirement"}
    assert template_variables(prompt_file, step="gaps") == {"agent.gaps"}
    assert template_variables(prompt_file) == set()


class _AspectsData(TypedDict, total=False):
    requirement: str


class _GapsData(TypedDict, total=False):
    gaps: str


def test_steps_matching_their_data_classes_have_no_errors(prompt_file):
    errors = step_agent_variable_errors(prompt_file, {"aspects": _AspectsData, "gaps": _GapsData})

    assert errors == []


def test_a_step_using_an_undeclared_variable_is_reported(prompt_file):
    errors = step_agent_variable_errors(prompt_file, {"aspects": _GapsData})

    assert errors == ["Step 'aspects' uses undeclared agent variables: ['agent.requirement']"]


def test_a_step_the_agent_needs_but_a_variant_lacks_is_reported(prompt_file):
    errors = step_agent_variable_errors(prompt_file, {"interpretation": _AspectsData})

    assert errors == ["Step 'interpretation' is missing in variant(s): A"]


def test_without_step_data_classes_nothing_is_checked(prompt_file):
    assert step_agent_variable_errors(prompt_file, {}) == []
