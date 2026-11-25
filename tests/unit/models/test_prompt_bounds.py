import pytest
from pydantic import ValidationError

from testbench_ai_service.models.prompt import PromptVariableDefinition


def _number(**kwargs) -> PromptVariableDefinition:
    return PromptVariableDefinition(name="Count", value_type="number", **kwargs)


@pytest.mark.parametrize(
    ("value", "problem"),
    [
        (5, None),
        (1, None),
        (100, None),
        (0.5, "must be at least 1."),
        (-3, "must be at least 1."),
        (101, "must be at most 100."),
        ("7", "a number is expected."),
        (True, "a number is expected."),
        (float("inf"), "a finite number is expected."),
    ],
)
def test_a_number_is_checked_against_type_and_bounds(value, problem):
    assert _number(minimum=1, maximum=100).problem_with(value) == problem


def test_a_number_without_bounds_accepts_any_finite_number():
    assert _number().problem_with(-1e12) is None


def test_other_types_are_checked_against_their_declaration():
    enum = PromptVariableDefinition(name="Mode", value_type="enum", choices=["keep", "replan"])
    assert enum.problem_with("keep") is None
    assert enum.problem_with("drop") == "must be one of: keep, replan."
    flag = PromptVariableDefinition(name="Flag", value_type="boolean")
    assert flag.problem_with(False) is None
    assert flag.problem_with("yes") == "true or false is expected."
    text = PromptVariableDefinition(name="Note", value_type="string")
    assert text.problem_with("x") is None
    assert text.problem_with(3) == "text is expected."


def test_bounds_are_only_for_numbers():
    with pytest.raises(ValidationError, match="only be set when value_type is 'number'"):
        PromptVariableDefinition(name="Note", value_type="string", minimum=1)


def test_the_minimum_may_not_exceed_the_maximum():
    with pytest.raises(ValidationError, match="must not be greater"):
        _number(minimum=10, maximum=1)


def test_the_default_must_lie_within_the_bounds():
    with pytest.raises(ValidationError, match="default_value"):
        _number(minimum=1, default_value=0)
    assert _number(minimum=1, default_value=40).default_value == 40
