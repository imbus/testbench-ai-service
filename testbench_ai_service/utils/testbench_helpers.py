from dataclasses import dataclass

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


@dataclass
class _TestCaseRow:
    unique_id: str
    values: dict[str, str]


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
