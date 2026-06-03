from testbench_cli_reporter.testbench import Connection as TBConnection

from testbench_ai_service.models.language import LanguageOption
from testbench_ai_service.models.testbench import (
    OptionalUser,
    RichTextInfo,
    SpecificationDetailsForUpdate,
)
from testbench_ai_service.utils.html_utils import (
    add_html_body_tags,
    build_disclaimer_html,
    escape_html,
    has_visible_text,
)
from testbench_ai_service.utils.i18n import get_translation
from testbench_ai_service.utils.testbench import patch_test_structure_element_spec
from testbench_ai_service.utils.time_utils import current_time


async def patch_description_generation_started_for_test_structure_element(
    conn: TBConnection,
    project_key: str,
    spec_key: str,
    previous_description: str,
    language: LanguageOption,
    user_key: str,
):
    generation_started_msg = get_translation("test_case_set_describer.run.started", language)
    generation_started_info = f"{current_time()} - {generation_started_msg}"
    if has_visible_text(previous_description):
        description_html = add_html_body_tags(
            f"{generation_started_info}<br/><br/>{previous_description}"
        )
    else:
        description_html = add_html_body_tags(generation_started_info)

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
    result_heading_msg = get_translation("test_case_set_describer.run.result_heading", language)
    result_heading = f"<b>{result_heading_msg} - {current_time()}</b>"
    disclaimer_msg = get_translation("shared.run.disclaimer", language)
    disclaimer_html = build_disclaimer_html(disclaimer_msg)
    description = escape_html(description)
    new_description = f"{result_heading}<br/>{description}{disclaimer_html}"
    if has_visible_text(previous_description):
        description_html = add_html_body_tags(f"{previous_description}<br/><br/>{new_description}")
    else:
        description_html = add_html_body_tags(new_description)

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
    failed_heading_msg = get_translation("test_case_set_describer.run.failed_heading", language)
    failed_heading = f"<b>{failed_heading_msg} - {current_time()}</b>"
    error_msg = get_translation("shared.run.error_message", language)
    error_html = f"{failed_heading}<br/>{error_msg}"
    if has_visible_text(previous_description):
        description_html = add_html_body_tags(f"{previous_description}<br/><br/>{error_html}")
    else:
        description_html = add_html_body_tags(error_html)

    spec_update = SpecificationDetailsForUpdate(
        reviewer=OptionalUser(optional=user_key),
        locker=OptionalUser(optional=None),
        description=RichTextInfo(html=description_html, images=[]),
    )
    return await patch_test_structure_element_spec(conn, project_key, spec_key, spec_update)
