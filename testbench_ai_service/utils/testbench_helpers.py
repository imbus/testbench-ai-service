from typing import Any

from testbench2robotframework.json_reader import TestCaseSet
from testbench2robotframework.model import KeywordCall, TestCaseDetails


def get_interaction_calls_for_test_case(test_case: TestCaseDetails) -> list[KeywordCall]:
    """
    Get the interaction calls that are shown in formatted test case string.

    Notes:
    - The returned list contains only high level interaction calls.
      The children of compound interaction calls are not included.
    """
    interaction_calls = []

    for interaction_call in test_case.testSequence:
        # Skip interaction call if it is child of a compound interaction
        if interaction_call.parentID is not None:
            continue

        interaction_calls.append(interaction_call)

    return interaction_calls


def get_parameter_combinations_as_string(test_case_set: TestCaseSet) -> str:
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
    simple_test_cases = []
    for test_case in test_case_set.test_cases.values():
        simple_test_cases.append(
            {
                "uniqueID": test_case.uniqueID,
                "values": {param.name: param.value for param in test_case.parameters},
            }
        )
    return _json_to_markdown_table(simple_test_cases)


def _json_to_markdown_table(data: list[dict[str, Any]]) -> str:
    all_keys_set: set[str] = set()
    for entry in data:
        all_keys_set.update(entry["values"].keys())
    all_keys = sorted(all_keys_set)

    # Prepare Markdown table header
    header = "| uniqueID | " + " | ".join(all_keys) + " |"
    separator = "|-----------|" + "|".join(["-" * (len(k) + 2) for k in all_keys]) + "|"

    # Prepare rows
    rows = []
    for entry in data:
        row_values = dict.fromkeys(all_keys, "")
        for key, val in entry["values"].items():
            row_values[key] = val
        row = "| " + entry["uniqueID"] + " | " + " | ".join(row_values[k] for k in all_keys) + " |"
        rows.append(row)

    # Combine everything
    return "\n".join([header, separator, *rows])
