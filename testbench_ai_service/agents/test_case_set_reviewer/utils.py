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


def get_test_case_set_as_string(test_case_set: TestCaseSet) -> str:
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

    interaction_calls = get_interaction_calls_for_test_case(first_test_case)
    for interaction_call in interaction_calls:
        # Init line with interaction name
        line = f"    {interaction_call.spec.name}"

        # Add parameters in format param:<parameter_name> if there are parameters
        if interaction_call.spec.callParameters:
            param_str = "    ".join(
                [
                    f"param:{param.name.replace('*', '').strip()}"
                    for param in interaction_call.spec.callParameters
                ]
            )
            line += f"    {param_str}"

        # Add step type if interaction type is not textual
        if interaction_call.spec.keywordType != KeywordType.Textual:
            step_type_str = (
                "step_type:check"
                if interaction_call.spec.callType == KeywordCallType.Check
                else "step_type:flow"
            )
            line += f"    {step_type_str}"

        lines.append(line)

    return "\n".join(lines)


async def patch_review_started_for_test_structure_element(
    conn: TBConnection,
    project_key: str,
    spec_key: str,
    previous_review_comment: str,
    language: LanguageOption,
    user_key: str,
):
    current_time = _current_time()
    review_started_message = get_translation("test_case_set_reviewer.run.started", language)
    review_comment_html = f"<html><body>{current_time} - {review_started_message}<br/><br/>{previous_review_comment}</body></html>"

    spec_update = SpecificationDetailsForUpdate(
        reviewer=OptionalUser(optional=user_key),
        locker=OptionalUser(optional=user_key),
        reviewComment=RichTextInfo(html=review_comment_html, images=[]),
    )
    return await patch_test_structure_element_spec(conn, project_key, spec_key, spec_update)


async def patch_review_result_for_test_structure_element(
    conn: TBConnection,
    project_key: str,
    spec_key: str,
    review_notes: str,
    previous_review_comment: str,
    language: LanguageOption,
    user_key: str,
):
    current_time = _current_time()
    heading = get_translation("test_case_set_reviewer.run.result_heading", language)
    ai_disclaimer = get_translation("shared.run.disclaimer", language)
    if not review_notes:
        review_notes = get_translation("test_case_set_reviewer.run.no_notes", language)
    review_notes = review_notes.replace("\n", "<br/>")
    review_comment_html = (
        f"<html><body><b>{heading} - {current_time}</b><br/>{review_notes}"
        f"<div style='padding-top: 5px;'><div style='border-top: 1px solid black; width: 218px; font-size: 10px;'>{ai_disclaimer}</div></div>"
        f"<br/>{previous_review_comment}</body></html>"
    )

    spec_update = SpecificationDetailsForUpdate(
        reviewer=OptionalUser(optional=user_key),
        locker=OptionalUser(optional=None),
        reviewComment=RichTextInfo(html=review_comment_html, images=[]),
    )
    return await patch_test_structure_element_spec(conn, project_key, spec_key, spec_update)


async def patch_previous_review_comment_for_test_structure_element(
    conn: TBConnection,
    project_key: str,
    spec_key: str,
    previous_review_comment: str,
    language: LanguageOption,
    user_key: str,
):
    current_time = _current_time()
    heading = get_translation("test_case_set_reviewer.run.failed_heading", language)
    error_message = get_translation("shared.run.error_message", language)
    review_comment_html = f"<html><body><b>{heading} - {current_time}</b><br/>{error_message}<br/><br/>{previous_review_comment}</body></html>"

    spec_update = SpecificationDetailsForUpdate(
        reviewer=OptionalUser(optional=user_key),
        locker=OptionalUser(optional=None),
        reviewComment=RichTextInfo(html=review_comment_html, images=[]),
    )
    return await patch_test_structure_element_spec(conn, project_key, spec_key, spec_update)
