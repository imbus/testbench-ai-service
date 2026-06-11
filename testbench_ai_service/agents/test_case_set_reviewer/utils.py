from pathlib import Path

from testbench_cli_reporter.testbench import Connection as TBConnection

from testbench_ai_service.models.language import LanguageOption
from testbench_ai_service.models.testbench import (
    OptionalUser,
    RichTextInfo,
    SpecificationDetailsForUpdate,
)
from testbench_ai_service.utils.html_utils import (
    add_html_body_tags,
    escape_html,
    has_visible_text,
)
from testbench_ai_service.utils.i18n import get_translation
from testbench_ai_service.utils.template_utils import load_template
from testbench_ai_service.utils.testbench import patch_test_structure_element_spec
from testbench_ai_service.utils.time_utils import current_time


async def patch_review_started_for_test_structure_element(
    conn: TBConnection,
    project_key: str,
    spec_key: str,
    previous_review_comment: str,
    language: LanguageOption,
    user_key: str,
    templates_dir: Path,
):
    template_path = templates_dir / language.value / "test_case_set_reviewer" / "started.jinja"
    review_started_info = load_template(template_path, {"current_time": current_time()})
    if has_visible_text(previous_review_comment):
        review_comment_html = add_html_body_tags(
            f"{review_started_info}<br/><br/>{previous_review_comment}"
        )
    else:
        review_comment_html = add_html_body_tags(review_started_info)

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
    templates_dir: Path,
):
    if not review_notes:
        review_notes = get_translation("test_case_set_reviewer.run.no_notes", language)
    template_path = templates_dir / language.value / "test_case_set_reviewer" / "template.jinja"
    new_review_comment = load_template(
        template_path,
        {
            "current_time": current_time(),
            "review_notes": escape_html(review_notes),
        },
    )
    if has_visible_text(previous_review_comment):
        review_comment_html = add_html_body_tags(
            f"{new_review_comment}<br/>{previous_review_comment}"
        )
    else:
        review_comment_html = add_html_body_tags(new_review_comment)

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
    templates_dir: Path,
):
    template_path = templates_dir / language.value / "test_case_set_reviewer" / "failed.jinja"
    error_html = load_template(template_path, {"current_time": current_time()})
    if has_visible_text(previous_review_comment):
        review_comment_html = add_html_body_tags(f"{error_html}<br/><br/>{previous_review_comment}")
    else:
        review_comment_html = add_html_body_tags(error_html)

    spec_update = SpecificationDetailsForUpdate(
        reviewer=OptionalUser(optional=user_key),
        locker=OptionalUser(optional=None),
        reviewComment=RichTextInfo(html=review_comment_html, images=[]),
    )
    return await patch_test_structure_element_spec(conn, project_key, spec_key, spec_update)
