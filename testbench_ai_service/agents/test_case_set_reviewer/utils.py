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


async def patch_review_started_for_test_structure_element(
    conn: TBConnection,
    project_key: str,
    spec_key: str,
    previous_review_comment: str,
    language: LanguageOption,
    user_key: str,
):
    review_started_message = get_translation("test_case_set_reviewer.run.started", language)
    review_comment_html = f"<html><body>{current_time()} - {review_started_message}<br/><br/>{previous_review_comment}</body></html>"

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
    heading = get_translation("test_case_set_reviewer.run.result_heading", language)
    ai_disclaimer = get_translation("shared.run.disclaimer", language)
    if not review_notes:
        review_notes = get_translation("test_case_set_reviewer.run.no_notes", language)
    review_notes = review_notes.replace("\n", "<br/>")
    review_comment_html = (
        f"<html><body><b>{heading} - {current_time()}</b><br/>{review_notes}"
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
    heading = get_translation("test_case_set_reviewer.run.failed_heading", language)
    error_message = get_translation("shared.run.error_message", language)
    review_comment_html = f"<html><body><b>{heading} - {current_time()}</b><br/>{error_message}<br/><br/>{previous_review_comment}</body></html>"

    spec_update = SpecificationDetailsForUpdate(
        reviewer=OptionalUser(optional=user_key),
        locker=OptionalUser(optional=None),
        reviewComment=RichTextInfo(html=review_comment_html, images=[]),
    )
    return await patch_test_structure_element_spec(conn, project_key, spec_key, spec_update)
