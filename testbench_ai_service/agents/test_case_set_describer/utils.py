from datetime import datetime
from zoneinfo import ZoneInfo

from testbench2robotframework.json_reader import TestCaseSet
from testbench2robotframework.model import (
    KeywordCallType,
    KeywordType,
)
from testbench_cli_reporter.testbench import Connection as TBConnection

from testbench_ai_service.models.language import LanguageOption
from testbench_ai_service.models.testbench import (
    OptionalUser,
    RichTextInfo,
    SpecificationDetailsForUpdate,
)
from testbench_ai_service.utils.i18n import get_translation
from testbench_ai_service.utils.testbench import patch_test_structure_element_spec
from testbench_ai_service.utils.testbench_helpers import get_interaction_calls_for_test_case

_TZ = ZoneInfo("Europe/Berlin")
_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def _current_time() -> str:
    return datetime.now(_TZ).strftime(_DATETIME_FORMAT)


def get_test_case_set_as_string(test_case_set: TestCaseSet) -> str:  # noqa: C901, PLR0912
    """
    Converts a test case set to a formatted string using the first test case in test case set.

    The output is structured as:
    - The test case set name on the first line
    - Each interaction (and its parameters, if any) indented on subsequent lines

    Note: Since test cases in a set differ only in their actual arguments,
    the first test case is representative for formatting purposes.

    Args:
        test_case_set: A test case set object

    Returns:
        str: Formatted string representing the test case set

    ## Example output:
    ```
    Endpreis berechnen ohne Rabatt - Instanz
        CarConfig starten    step_type:flow
        Fahrzeug wählen    Fahrzeugname='Rolo'    step_type:flow
        Sondermodell wählen    Sondermodell=${Special}    step_type:flow
        Zubehör wählen    Zubehörname=${Zubehörname}    step_type:flow
        Preis prüfen    Preis=${Preis}    step_type:check
        CarConfig beenden    step_type:flow
    ```
    """
    first_test_case = next(iter(test_case_set.test_cases.values()))

    # Add test case set name as first line
    lines = [f"{test_case_set.details.name}"]
    interaction_calls = []
    previous_call = None
    formatted_steps = []
    interaction_calls_for_test_case = get_interaction_calls_for_test_case(first_test_case)
    for call in interaction_calls_for_test_case:
        # Init line with interaction name
        line = f"    {call.spec.name}"
        if previous_call and call.spec.key == previous_call.spec.key:
            for param in call.spec.callParameters:
                if (
                    param.parameterValue is None
                    and "parameter" in formatted_steps[-1]
                    and param.name in formatted_steps[-1]["parameter"]
                ):
                    param_value = formatted_steps[-1]["parameter"].get(param.name, None)
                    if isinstance(param_value, list):
                        param_value.append(param.value)
                        formatted_steps[-1]["parameter"][param.name] = param_value
                    else:
                        value_str = param.value if param.value is not None else "-"
                        formatted_steps[-1]["parameter"][param.name] = [param_value, value_str]
            continue

        # Add parameters in format param:<parameter_name> if there are parameters
        params = {}
        if call.spec.callParameters:
            for param in call.spec.callParameters:
                if param.parameterValue is not None:
                    params[param.name] = f"${{{param.parameterValue.name}}}"
                else:
                    params[param.name] = f"{param.value or '-'}"
        interaction_calls.append(call)
        previous_call = call

        # Add step type if interaction type is not textual
        step_type_str = ""
        if call.spec.keywordType != KeywordType.Textual:
            step_type_str = (
                "step_type:check"
                if call.spec.callType == KeywordCallType.Check
                else "step_type:flow"
            )

        formatted_steps.append({"name": call.spec.name, "parameter": params, "type": step_type_str})

    for keyword in formatted_steps:
        line = f"    {keyword.get('name', None)}    "
        for param_name, param_value in keyword.get("parameter", {}).items():
            if isinstance(param_value, str) and param_value.startswith("${"):
                line += f"{param_name}={param_value}    "
            else:
                line += f"{param_name}={param_value!r}    "
        line += f"{keyword.get('type', None)}"
        lines.append(line)

    return "\n".join(lines)


async def patch_description_generation_started_for_test_structure_element(
    conn: TBConnection,
    project_key: str,
    spec_key: str,
    previous_description: str,
    language: LanguageOption,
    user_key: str,
):
    current_time = _current_time()
    description_generation_started_message = get_translation(
        "test_case_set_describer.run.started", language
    )
    description_html = f"<html><body>{current_time} - {description_generation_started_message}<br/><br/>{previous_description}</body></html>"

    spec_update = SpecificationDetailsForUpdate(
        reviewer=OptionalUser(optional=user_key),
        locker=OptionalUser(optional=user_key),
        description=RichTextInfo(html=description_html, images=[]),
    )
    return await patch_test_structure_element_spec(conn, project_key, spec_key, spec_update)


async def patch_generated_description_for_test_structure_element(
    conn: TBConnection,
    project_key: str,
    spec_key: str,
    description: str,
    previous_description: str,
    language: LanguageOption,
    user_key: str,
):
    current_time = _current_time()
    heading = get_translation("test_case_set_describer.run.result_heading", language)
    ai_disclaimer = get_translation("shared.run.disclaimer", language)
    description = description.replace("\n", "<br/>")
    if previous_description.replace("\n", "").strip():
        description_html = (
            f"<html><body>{previous_description}<br/><br/><b>{heading} - {current_time}</b><br/>{description}"
            f"<div style='padding-top: 5px;'><div style='border-top: 1px solid black; width: 218px; font-size: 10px;'>{ai_disclaimer}</div></div></body></html>"
        )
    else:
        description_html = (
            f"<html><body><b>{heading} - {current_time}</b><br/>{description}</body></html>"
        )

    spec_update = SpecificationDetailsForUpdate(
        locker=OptionalUser(optional=None),
        reviewer=OptionalUser(optional=user_key),
        description=RichTextInfo(html=description_html, images=[]),
    )
    return await patch_test_structure_element_spec(conn, project_key, spec_key, spec_update)


async def patch_previous_description_for_test_structure_element(
    conn: TBConnection,
    project_key: str,
    spec_key: str,
    previous_description: str,
    language: LanguageOption,
    user_key: str,
):
    current_time = _current_time()
    heading = get_translation("test_case_set_describer.run.failed_heading", language)
    error_message = get_translation("shared.run.error_message", language)
    description_html = f"<html><body>{previous_description}<br/><br/><b>{heading} - {current_time}</b><br/>{error_message}</body></html>"

    spec_update = SpecificationDetailsForUpdate(
        reviewer=OptionalUser(optional=user_key),
        locker=OptionalUser(optional=None),
        description=RichTextInfo(html=description_html, images=[]),
    )
    return await patch_test_structure_element_spec(conn, project_key, spec_key, spec_update)
