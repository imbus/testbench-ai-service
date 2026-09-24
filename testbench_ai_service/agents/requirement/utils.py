import asyncio
from pathlib import Path

from testbench_cli_reporter.testbench import Connection as TBConnection

from testbench_ai_service.log import logger
from testbench_ai_service.models.language import LanguageOption
from testbench_ai_service.models.testbench import (
    FilteringOptions,
    OptionalUser,
    RequirementAssignment,
    RichTextInfo,
    SpecificationDetailsForUpdate,
)
from testbench_ai_service.utils.html_utils import escape_html, has_visible_text
from testbench_ai_service.utils.template_utils import render_template, resolve_template_path
from testbench_ai_service.utils.testbench import (
    get_requirements,
    patch_test_structure_element_spec,
)
from testbench_ai_service.utils.time_utils import current_time


async def load_requirements(
    conn: TBConnection,
    project_key: str,
    root_uid: str,
    tov_key: str,
    cycle_key: str | None = None,
    filtering: FilteringOptions | None = None,
) -> list[RequirementAssignment]:
    """Load the requirements assigned below a tree root of a TOV or cycle.

    Args:
        conn: The active TestBench connection.
        project_key: Key of the project owning the TOV.
        root_uid: Unique ID of the tree root the requirements are limited to.
        tov_key: Key of the TOV whose requirements are loaded.
        cycle_key: Key of a cycle to load the requirements of instead of the TOV's.
        filtering: Optional filters applied when loading the requirements.

    Returns:
        The requirements assigned below ``root_uid``.
    """
    logger.debug("Loading requirements of TOV '%s' (cycle '%s')", tov_key, cycle_key)
    return await asyncio.to_thread(
        get_requirements,
        conn,
        project_key,
        root_uid,
        tov_key,
        cycle_key=cycle_key,
        filtering=filtering,
    )


#: Agent key used to resolve this agent's write-back templates.
AGENT_KEY = "requirement"


async def patch_generation_started(
    conn: TBConnection,
    project_key: str,
    spec_key: str,
    previous_description: str,
    language: LanguageOption,
    user_key: str,
    templates_dir: Path,
):
    """Mark a theme as having test idea generation in progress, and lock it.

    Args:
        conn: The active TestBench connection.
        project_key: Key of the project owning the specification.
        spec_key: The theme specification to patch.
        previous_description: The description to preserve below the marker.
        language: Language of the rendered marker.
        user_key: The triggering user, recorded as locker and reviewer.
        templates_dir: Root of the write-back templates.
    """
    template_path = resolve_template_path(
        "started.jinja", templates_dir=templates_dir, language=language, agent_key=AGENT_KEY
    )
    description_html = render_template(
        template_path,
        {
            "current_time": current_time(),
            "previous_description": previous_description
            if has_visible_text(previous_description)
            else None,
        },
    )
    spec_update = SpecificationDetailsForUpdate(
        reviewer=OptionalUser(optional=user_key),
        locker=OptionalUser(optional=user_key),
        description=RichTextInfo(html=description_html, images=[]),
    )
    return await patch_test_structure_element_spec(conn, project_key, spec_key, spec_update)


async def patch_generated_test_ideas(
    conn: TBConnection,
    project_key: str,
    spec_key: str,
    test_ideas: str,
    previous_description: str,
    language: LanguageOption,
    user_key: str,
    templates_dir: Path,
):
    """Write the generated test ideas into a theme's description and unlock it.

    Args:
        conn: The active TestBench connection.
        project_key: Key of the project owning the specification.
        spec_key: The theme specification to patch.
        test_ideas: The model's output, escaped before rendering.
        previous_description: The description to preserve above the ideas.
        language: Language of the rendered wrapper.
        user_key: The triggering user, recorded as reviewer.
        templates_dir: Root of the write-back templates.
    """
    template_path = resolve_template_path(
        "template.jinja", templates_dir=templates_dir, language=language, agent_key=AGENT_KEY
    )
    description_html = render_template(
        template_path,
        {
            "current_time": current_time(),
            "description": escape_html(test_ideas),
            "previous_description": previous_description
            if has_visible_text(previous_description)
            else None,
        },
    )
    spec_update = SpecificationDetailsForUpdate(
        locker=OptionalUser(optional=None),
        reviewer=OptionalUser(optional=user_key),
        description=RichTextInfo(html=description_html, images=[]),
    )
    return await patch_test_structure_element_spec(conn, project_key, spec_key, spec_update)


async def patch_generation_failed(
    conn: TBConnection,
    project_key: str,
    spec_key: str,
    previous_description: str,
    language: LanguageOption,
    user_key: str,
    templates_dir: Path,
):
    """Restore a theme's previous description after a failure, and unlock it.

    Args:
        conn: The active TestBench connection.
        project_key: Key of the project owning the specification.
        spec_key: The theme specification to patch.
        previous_description: The description to restore.
        language: Language of the rendered notice.
        user_key: The triggering user, recorded as reviewer.
        templates_dir: Root of the write-back templates.
    """
    template_path = resolve_template_path(
        "failed.jinja", templates_dir=templates_dir, language=language, agent_key=AGENT_KEY
    )
    description_html = render_template(
        template_path,
        {
            "current_time": current_time(),
            "previous_description": previous_description
            if has_visible_text(previous_description)
            else None,
        },
    )
    spec_update = SpecificationDetailsForUpdate(
        reviewer=OptionalUser(optional=user_key),
        locker=OptionalUser(optional=None),
        description=RichTextInfo(html=description_html, images=[]),
    )
    return await patch_test_structure_element_spec(conn, project_key, spec_key, spec_update)
