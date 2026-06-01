from testbench_cli_reporter.testbench import Connection as TBConnection

from testbench_ai_service.models.language import LanguageOption
from testbench_ai_service.models.testbench import (
    OptionalUser,
    RichTextInfo,
    SpecificationDetailsForUpdate,
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
    description_generation_started_message = get_translation(
        "test_case_set_describer.run.started", language
    )
    description_html = f"<html><body>{current_time()} - {description_generation_started_message}<br/><br/>{previous_description}</body></html>"

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
    heading = get_translation("test_case_set_describer.run.result_heading", language)
    ai_disclaimer = get_translation("shared.run.disclaimer", language)
    description = description.replace("\n", "<br/>")
    if previous_description.replace("\n", "").strip():
        description_html = (
            f"<html><body>{previous_description}<br/><br/><b>{heading} - {current_time()}</b><br/>{description}"
            f"<div style='padding-top: 5px;'><div style='border-top: 1px solid black; width: 218px; font-size: 10px;'>{ai_disclaimer}</div></div></body></html>"
        )
    else:
        description_html = (
            f"<html><body><b>{heading} - {current_time()}</b><br/>{description}</body></html>"
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
    heading = get_translation("test_case_set_describer.run.failed_heading", language)
    error_message = get_translation("shared.run.error_message", language)
    description_html = f"<html><body>{previous_description}<br/><br/><b>{heading} - {current_time()}</b><br/>{error_message}</body></html>"

    spec_update = SpecificationDetailsForUpdate(
        reviewer=OptionalUser(optional=user_key),
        locker=OptionalUser(optional=None),
        description=RichTextInfo(html=description_html, images=[]),
    )
    return await patch_test_structure_element_spec(conn, project_key, spec_key, spec_update)
