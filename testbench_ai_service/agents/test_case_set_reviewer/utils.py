from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from testbench2robotframework.json_reader import TestCaseSet
from testbench2robotframework.model import (
    KeywordCallType,
    KeywordType,
)
from testbench_cli_reporter.testbench import Connection as TBConnection

from testbench_ai_service.agents.test_case_set_reviewer.models import (
    DEFAULT_ENGLISH_GLOSSARY,
    DEFAULT_GERMAN_GLOSSARY,
)
from testbench_ai_service.config import (
    PromptConfig,
)
from testbench_ai_service.models.language import LanguageOption
from testbench_ai_service.models.testbench import (
    OptionalUser,
    RichTextInfo,
    SpecificationDetailsForUpdate,
    TestCaseSetDetails,
)
from testbench_ai_service.utils.i18n import get_translation
from testbench_ai_service.utils.string_processor import (
    strip_html_body_tags,
)
from testbench_ai_service.utils.testbench import patch_test_structure_element_spec
from testbench_ai_service.utils.testbench_helpers import get_interaction_calls_for_test_case


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


def get_test_case_glossary(language: LanguageOption, prompt_config: PromptConfig) -> str:
    """
    Retrieve the glossary for a test case based on language and prompt configuration.

    If the prompt configuration contains a glossary string, attempts to read the file if it exists,
    otherwise returns the string.
    If no glossary is provided, returns a default glossary based on the specified language.
    """
    glossary = getattr(prompt_config, "glossary", None)
    if glossary is not None:
        path = Path(glossary)
        if path.is_file():
            return path.read_text(encoding="utf-8")
        return str(glossary)
    return (
        DEFAULT_GERMAN_GLOSSARY if language == LanguageOption.GERMAN else DEFAULT_ENGLISH_GLOSSARY
    )


async def get_review_comment_for_test_case_set(
    conn: TBConnection, project_key: str, test_case_set_key: str
):
    tcs_data = conn.get_project_test_case_set(project_key, test_case_set_key)
    tcs = TestCaseSetDetails.model_validate(tcs_data)
    return strip_html_body_tags(tcs.spec.reviewComment)


async def patch_review_started_for_test_structure_element(
    conn: TBConnection,
    project_key: str,
    spec_key: str,
    previous_review_comment: str,
    language: LanguageOption,
    user_key: str,
):
    current_time = f"{datetime.now(ZoneInfo('Europe/Berlin')).strftime('%Y-%m-%d %H:%M:%S')}"
    review_started_message = get_translation("review_started_message", language)
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
    current_time = f"{datetime.now(ZoneInfo('Europe/Berlin')).strftime('%Y-%m-%d %H:%M:%S')}"
    heading = get_translation("review_result_heading", language)
    ai_disclaimer = get_translation("disclaimer", language)
    if not review_notes:
        review_notes = get_translation("review_result_no_notes", language)
    review_notes = review_notes.replace("\n", "<br/>")
    review_comment_html = (
        f"<html><body><b>{heading} - {current_time}</b><br/>{review_notes}"
        f"<div style='padding: 5px;'><div style='border-top: 1px solid black; width: 50%; font-size: 10px;'>{ai_disclaimer}</div></div>"
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
    current_time = f"{datetime.now(ZoneInfo('Europe/Berlin')).strftime('%Y-%m-%d %H:%M:%S')}"
    failed = get_translation("review_failed", language)
    error_message = get_translation("error_message", language)
    review_comment_html = f"<html><body><b>{failed} - {current_time}</b><br/>{error_message}<br/><br/>{previous_review_comment}</body></html>"

    spec_update = SpecificationDetailsForUpdate(
        reviewer=OptionalUser(optional=user_key),
        locker=OptionalUser(optional=None),
        reviewComment=RichTextInfo(html=review_comment_html, images=[]),
    )
    return await patch_test_structure_element_spec(conn, project_key, spec_key, spec_update)
