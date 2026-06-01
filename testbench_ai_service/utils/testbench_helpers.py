from dataclasses import dataclass

from testbench2robotframework.json_reader import TestCaseSet
from testbench2robotframework.model import (
    KeywordCall,
    KeywordCallType,
    KeywordType,
    ParameterSummary,
    TestCaseDetails,
)


def get_keyword_calls_for_test_case(test_case: TestCaseDetails) -> list[KeywordCall]:
    """
    Get the keyword calls that are shown in formatted test case string.

    Notes:
    - The returned list contains only high level keyword calls.
      The children of compound keyword calls are not included.
    """
    keyword_calls = []
    for keyword_call in test_case.testSequence:
        if keyword_call.parentID is not None:
            continue
        keyword_calls.append(keyword_call)
    return keyword_calls


@dataclass
class _TestCaseRow:
    unique_id: str
    values: dict[str, str]


def parameter_combinations_as_str(test_case_set: TestCaseSet) -> str:
    """
    Converts the parameter combinations of a test case set to a Markdown table string.

    ## Example output:
    ```
    | Fahrzeug | Sondermodell |
    | --- | --- |
    | January | $250 |
    | February | $80 |
    | March | $420 |
    ```
    """
    rows = [
        _TestCaseRow(
            unique_id=test_case.uniqueID,
            values={
                param.name: param.value if param.value is not None else ""
                for param in test_case.parameters
            },
        )
        for test_case in test_case_set.test_cases.values()
    ]
    return _to_markdown_table(rows)


def _to_markdown_table(rows: list[_TestCaseRow]) -> str:
    all_keys = sorted({key for row in rows for key in row.values})

    header = "| uniqueID | " + " | ".join(all_keys) + " |"
    separator = "|-----------|" + "|".join(["-" * (len(k) + 2) for k in all_keys]) + "|"

    table_rows = [
        "| " + row.unique_id + " | " + " | ".join(row.values.get(k, "") for k in all_keys) + " |"
        for row in rows
    ]

    return "\n".join([header, separator, *table_rows])


@dataclass
class _StepData:
    name: str
    params: dict[str, "str | list[str]"]
    step_type: str


def _param_value_string(param: ParameterSummary) -> str:
    """Return the string representation for a single call parameter."""
    if param.parameterValue is not None:
        return f"${{{param.parameterValue.name}}}"
    return param.value if param.value is not None else "-"


def _make_step_data(call: KeywordCall) -> _StepData:
    """Build a _StepData from a single keyword call."""
    params: dict[str, str | list[str]] = {
        param.name: _param_value_string(param) for param in (call.spec.callParameters or [])
    }
    step_type = ""
    if call.spec.keywordType != KeywordType.Textual:
        if call.spec.callType == KeywordCallType.Check:
            step_type = "step_type:check"
        else:
            step_type = "step_type:flow"
    return _StepData(name=call.spec.name, params=params, step_type=step_type)


def _merge_literal_params(step: _StepData, call: KeywordCall) -> None:
    """Merge literal parameter values from a duplicate consecutive keyword call into *step*.

    Abstract parameters (those backed by a parameter table entry) are not merged
    because they are identical across consecutive duplicate steps by definition.
    """
    for param in call.spec.callParameters or []:
        if param.parameterValue is not None or param.name not in step.params:
            continue
        new_value = param.value if param.value is not None else "-"
        existing = step.params[param.name]
        if isinstance(existing, list):
            existing.append(new_value)
        else:
            step.params[param.name] = [existing, new_value]


def _collect_steps(keyword_calls: list[KeywordCall]) -> list[_StepData]:
    """Convert a flat keyword-call list into deduplicated _StepData entries.

    Consecutive calls that share the same ``spec.key`` are collapsed into one
    step; their literal parameter values are accumulated into a list.
    """
    steps: list[_StepData] = []
    prev_key = None
    for call in keyword_calls:
        if prev_key is not None and call.spec.key == prev_key:
            _merge_literal_params(steps[-1], call)
            continue
        steps.append(_make_step_data(call))
        prev_key = call.spec.key
    return steps


def _render_step(step: _StepData) -> str:
    """Format a single step as an indented line with parameters and step type."""
    parts = [f"    {step.name}"]
    for param_name, param_value in step.params.items():
        if isinstance(param_value, str) and param_value.startswith("${"):
            parts.append(f"{param_name}={param_value}")
        else:
            parts.append(f"{param_name}={param_value!r}")
    if step.step_type:
        parts.append(step.step_type)
    return "    ".join(parts)


def test_case_set_as_str(test_case_set: TestCaseSet) -> str:
    """
    Converts a test case set to a formatted string using the first test case in the set.

    The output is structured as:
    - The test case set name on the first line
    - Each step (and its parameters, if any) indented on subsequent lines

    Parameters of each step are rendered as:
    - ``param_name=${ParameterName}`` when the value comes from the parameter table
    - ``param_name='literal_value'`` when the value is hardcoded at design time

    Consecutive steps with the same ``spec.key`` are collapsed into one step;
    their literal parameter values are accumulated into a list.

    Note: Since test cases in a set differ only in their actual arguments,
    the first test case is representative for formatting purposes.

    Args:
        test_case_set: A test case set object

    Returns:
        Formatted string representing the test case set

    ## Example output:
    ```
    Endpreis berechnen ohne Rabatt - Instanz
        CarConfig starten    step_type:flow
        Fahrzeug wählen    Fahrzeugname=${Fahrzeugname}    step_type:flow
        Sondermodell wählen    Sondermodell=${Sondermodell}    step_type:flow
        Preis prüfen    Preis=${Preis}    step_type:check
        CarConfig beenden    step_type:flow
    ```
    """
    lines = [test_case_set.details.name]
    first_test_case = next(iter(test_case_set.test_cases.values()))
    keyword_calls = get_keyword_calls_for_test_case(first_test_case)
    steps = _collect_steps(keyword_calls)
    for step in steps:
        lines.append(_render_step(step))
    return "\n".join(lines)
