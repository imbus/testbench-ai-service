import asyncio
import re
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path

from requests import HTTPError
from testbench_cli_reporter.testbench import Connection as TBConnection

from testbench_ai_service.agents.generate_test_ideas.context import html_text
from testbench_ai_service.agents.generate_test_ideas.model import (
    ExistingTestCaseSet,
    Requirement,
    TestIdea,
    TestIdeaResult,
    Theme,
    ThemeContext,
)
from testbench_ai_service.log import logger
from testbench_ai_service.models.language import LanguageOption
from testbench_ai_service.models.testbench import (
    FilteringOptions,
    OptionalUser,
    Priority,
    RequirementAssignment,
    RichTextInfo,
    SpecificationDetailsForUpdate,
    TestCaseSetNode,
    TestStructureTree,
    TestThemeNode,
    TestThemeSpecification,
)
from testbench_ai_service.utils.html_utils import (
    add_html_body_tags,
    escape_html,
    has_visible_text,
)
from testbench_ai_service.utils.i18n import get_translation
from testbench_ai_service.utils.template_utils import render_template, resolve_template_path
from testbench_ai_service.utils.testbench import (
    create_test_case_set,
    delete_test_case_set,
    get_requirements,
    get_test_case_set_details,
    get_test_theme_details,
    patch_test_structure_element_spec,
)
from testbench_ai_service.utils.time_utils import current_time

#: Agent key used to resolve this agent's write-back templates.
AGENT_KEY = "requirement"

#: Upper bound on the requests to TestBench in flight at once.
TB_MAX_CONCURRENT_REQUESTS = 4

#: Length a test case set's description is cut to in the prompt.
DESCRIPTION_SHORT_MAX_CHARS = 300

#: First TestBench version with an endpoint to create test case sets.
CREATE_TEST_CASE_SETS_MIN_VERSION = [5, 0]

#: Characters TestBench rejects in the name of a new test case set (422).
FORBIDDEN_NAME_CHARS = re.compile(r"[/.,'<;>&]")

#: Longest name TestBench accepts for a test case set.
NAME_MAX_CHARS = 255


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
    keep_locked: bool = False,
):
    """Write the generated test ideas into a theme's description and restore its lock.

    Args:
        conn: The active TestBench connection.
        project_key: Key of the project owning the specification.
        spec_key: The theme specification to patch.
        test_ideas: The rendered test ideas, escaped before rendering.
        previous_description: The description to preserve above the ideas.
        language: Language of the rendered wrapper.
        user_key: The triggering user, recorded as reviewer.
        templates_dir: Root of the write-back templates.
        keep_locked: Leave the theme locked by the user, who held the lock before the run.
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
        locker=OptionalUser(optional=user_key if keep_locked else None),
        reviewer=OptionalUser(optional=user_key),
        description=RichTextInfo(html=description_html, images=[]),
    )
    return await patch_test_structure_element_spec(conn, project_key, spec_key, spec_update)


async def patch_previous_description(
    conn: TBConnection,
    project_key: str,
    spec_key: str,
    previous_description: str,
    user_key: str,
    keep_locked: bool = False,
):
    """Put back a theme's previous description, without any test ideas, and restore its lock.

    Used when the ideas became test case sets: they live in the sets, so the
    theme keeps only what it said before the run.

    Args:
        conn: The active TestBench connection.
        project_key: Key of the project owning the specification.
        spec_key: The theme specification to patch.
        previous_description: The description from before the run, without body tags.
        user_key: The triggering user, recorded as reviewer.
        keep_locked: Leave the theme locked by the user, who held the lock before the run.
    """
    spec_update = SpecificationDetailsForUpdate(
        reviewer=OptionalUser(optional=user_key),
        locker=OptionalUser(optional=user_key if keep_locked else None),
        description=RichTextInfo(html=add_html_body_tags(previous_description), images=[]),
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
    keep_locked: bool = False,
):
    """Restore a theme's previous description and lock after a failure.

    Args:
        conn: The active TestBench connection.
        project_key: Key of the project owning the specification.
        spec_key: The theme specification to patch.
        previous_description: The description to restore.
        language: Language of the rendered notice.
        user_key: The triggering user, recorded as reviewer.
        templates_dir: Root of the write-back templates.
        keep_locked: Leave the theme locked by the user, who held the lock before the run.
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
        locker=OptionalUser(optional=user_key if keep_locked else None),
        description=RichTextInfo(html=description_html, images=[]),
    )
    return await patch_test_structure_element_spec(conn, project_key, spec_key, spec_update)


async def get_theme_spec(
    conn: TBConnection, project_key: str, theme: TestThemeNode
) -> TestThemeSpecification:
    """Read a test theme's specification.

    Read before the theme is marked as in progress: afterwards its description is
    the progress marker and its locker the triggering user.

    Args:
        conn: The active TestBench connection.
        project_key: Key of the project owning the theme.
        theme: The theme to read.

    Returns:
        The theme's specification as it stands.
    """
    details = await asyncio.to_thread(get_test_theme_details, conn, project_key, theme.base.key)
    return details.spec


async def get_test_theme(
    conn: TBConnection,
    project_key: str,
    tree: TestStructureTree,
    theme: TestThemeNode,
    spec: TestThemeSpecification,
    requirements: list[Requirement],
) -> ThemeContext:
    """Gather what the target theme and everything below it already contain.

    The tree nodes carry names only, so each test case set's details are read to
    learn its description and the requirements it is linked to.

    Args:
        conn: The active TestBench connection.
        project_key: Key of the project owning the theme.
        tree: The test structure tree loaded below the theme.
        theme: The target theme, the root of ``tree``.
        spec: The theme's specification, as read by :func:`get_theme_spec` before
            generation started.
        requirements: The theme's requirements.

    Returns:
        The theme's context for the prompt.
    """
    subthemes: list[str] = []
    test_case_set_nodes: list[TestCaseSetNode] = []
    for node in tree.nodes:
        if isinstance(node, TestThemeNode) and node.base.key != theme.base.key:
            subthemes.append(_relative_path(node, theme))
        elif isinstance(node, TestCaseSetNode):
            test_case_set_nodes.append(node)

    semaphore = asyncio.Semaphore(TB_MAX_CONCURRENT_REQUESTS)

    async def _existing(node: TestCaseSetNode) -> ExistingTestCaseSet:
        async with semaphore:
            tcs = await asyncio.to_thread(
                get_test_case_set_details, conn, project_key, node.base.key
            )
        return ExistingTestCaseSet(
            key=node.base.key,
            title=node.base.name,
            path=_relative_path(node, theme),
            description_short=_shorten(html_text(tcs.spec.description)),
            requirement_keys=[reference.key for reference in tcs.spec.requirements],
        )

    existing_test_case_sets = await asyncio.gather(
        *(_existing(node) for node in test_case_set_nodes)
    )

    return ThemeContext(
        theme=Theme(
            key=theme.base.key,
            title=theme.base.name,
            description=spec.description,
            review_comment=spec.reviewComment,
            path=[segment for segment in theme.base.path.split("/") if segment],
            priority=None if spec.priority == Priority.Undefined else spec.priority.value,
            tags=[tag.name for tag in spec.tags],
            udfs={udf.name: udf.value for udf in spec.udfs if udf.value.strip()},
        ),
        requirements=requirements,
        existing_subthemes=subthemes,
        existing_test_case_sets=list(existing_test_case_sets),
    )


def _relative_path(node: TestThemeNode | TestCaseSetNode, theme: TestThemeNode) -> str:
    """Return a node's path below the theme, e.g. ``Subtheme/Test case set``."""
    return node.base.path.removeprefix(f"{theme.base.path}/")


def _shorten(text: str, limit: int = DESCRIPTION_SHORT_MAX_CHARS) -> str:
    """Collapse whitespace and cut the text to ``limit`` characters."""
    text = " ".join(text.split())
    return text if len(text) <= limit else f"{text[: limit - 1].rstrip()}…"


def render_test_ideas(
    result: TestIdeaResult, requirements: list[Requirement], language: LanguageOption
) -> str:
    """Render the validated test ideas as the plain text written into the theme.

    A header lists the theme's requirements, followed by the numbered subthemes
    with their ideas and then the ideas directly under the theme. An empty result
    renders the header and a notice that no ideas were generated.

    Args:
        result: The test ideas after :func:`apply_guardrails`.
        requirements: The theme's requirements, for the header.
        language: Language of the labels.

    Returns:
        The rendered text, unescaped.
    """
    test_theme = get_translation("requirement.run.test_theme", language)
    test_case = get_translation("requirement.run.test_case", language)
    covers = get_translation("requirement.run.covers", language)

    def _idea(number: str, idea: TestIdea, indent: str) -> list[str]:
        lines = [f"{indent}{number} {test_case}: {idea.title}"]
        body = [*idea.description.splitlines()]
        if idea.covered_requirements:
            body.append(f"{covers}: {', '.join(idea.covered_requirements)}")
        lines.extend(f"{indent}   {line}" if line.strip() else "" for line in body)
        return lines

    header = [get_translation("requirement.run.ideas_for", language)]
    header.extend(
        f"{requirement.external_ref or requirement.key}: {requirement.title}"
        for requirement in requirements
    )
    entries: list[list[str]] = []
    number = 0
    for group in result.groups:
        if group.theme_name is None:
            for idea in group.ideas:
                number += 1
                entries.append(_idea(str(number), idea, ""))
            continue
        number += 1
        entry = [f"{number} {test_theme}: {group.theme_name}"]
        for index, idea in enumerate(group.ideas, start=1):
            entry.append("")
            entry.extend(_idea(f"{number}.{index}", idea, "   "))
        entries.append(entry)
    if not entries:
        entries.append([get_translation("requirement.run.no_ideas", language)])

    return "\n\n".join("\n".join(block) for block in [header, *entries])


class TestCaseSetCreationForbiddenError(Exception):
    """TestBench refused to create the first test case set with 403.

    Typically a JWT without ``ModifyTestStructureElements``. Nothing was created.
    """


@dataclass(frozen=True)
class CreatedTestCaseSet:
    """A test case set created by the agent, kept for the rollback."""

    key: str
    spec_key: str


def test_case_set_name(title: str, number: int, language: LanguageOption) -> str:
    """Turn an idea's title into a name TestBench accepts for a test case set.

    Characters TestBench rejects become spaces, whitespace is collapsed and the
    name is cut to :data:`NAME_MAX_CHARS`. A title with nothing left falls back to
    the translated "Test case <number>".

    Args:
        title: The idea's title.
        number: Position of the idea, for the fallback name.
        language: Language of the fallback name.

    Returns:
        A non-empty name of at most :data:`NAME_MAX_CHARS` characters.
    """
    name = " ".join(FORBIDDEN_NAME_CHARS.sub(" ", title).split())[:NAME_MAX_CHARS].rstrip()
    return name or f"{get_translation('requirement.run.test_case', language)} {number}"


def render_test_case_set_description(
    idea: TestIdea, language: LanguageOption, templates_dir: Path
) -> str:
    """Render the HTML description of the test case set created for an idea.

    Args:
        idea: The idea after :func:`apply_guardrails`.
        language: Language of the labels and template.
        templates_dir: Root of the write-back templates.

    Returns:
        A full ``<html><body>`` document with the escaped idea.
    """
    lines = [*idea.description.splitlines()]
    if idea.covered_requirements:
        covers = get_translation("requirement.run.covers", language)
        lines.append(f"{covers}: {', '.join(idea.covered_requirements)}")
    template_path = resolve_template_path(
        "test_case_set.jinja", templates_dir=templates_dir, language=language, agent_key=AGENT_KEY
    )
    return render_template(
        template_path,
        {"current_time": current_time(), "description": escape_html("\n".join(lines))},
    )


async def create_test_case_sets(
    conn: TBConnection,
    project_key: str,
    tov_key: str,
    theme_key: str,
    result: TestIdeaResult,
    language: LanguageOption,
    templates_dir: Path,
    created: list[CreatedTestCaseSet],
) -> None:
    """Create one test case set per idea, flat below the theme, in the ideas' order.

    TestBench cannot create test themes, so the subtheme grouping of the ideas is
    dropped. Each set is created locked, given the
    idea as its description and unlocked again. Every created set is appended to
    ``created`` right away, so the caller can roll back what exists when a later
    step fails.

    Args:
        conn: The active TestBench connection.
        project_key: Key of the project owning the theme.
        tov_key: Key of the TOV the theme belongs to.
        theme_key: Element key of the theme the sets are created under.
        result: The ideas after :func:`apply_guardrails`.
        language: Language of the descriptions.
        templates_dir: Root of the write-back templates.
        created: Receives every set created, in order.

    Raises:
        TestCaseSetCreationForbiddenError: TestBench answered the first creation with 403.
        Exception: Any other TestBench error; ``created`` lists what exists.
    """
    for number, idea in enumerate(result.ideas, start=1):
        name = test_case_set_name(idea.title, number, language)
        try:
            details = await asyncio.to_thread(
                create_test_case_set,
                conn,
                project_key,
                tov_key,
                theme_key,
                name,
                keep_locked=True,
            )
        except HTTPError as error:
            status = error.response.status_code if error.response is not None else None
            if status == HTTPStatus.FORBIDDEN and not created:
                body = error.response.text.strip() if error.response is not None else ""
                raise TestCaseSetCreationForbiddenError(body or str(error)) from error
            raise
        created.append(CreatedTestCaseSet(key=details.key, spec_key=details.spec.key))
        await patch_test_structure_element_spec(
            conn,
            project_key,
            details.spec.key,
            SpecificationDetailsForUpdate(
                locker=OptionalUser(optional=None),
                description=RichTextInfo(
                    html=render_test_case_set_description(idea, language, templates_dir),
                    images=[],
                ),
            ),
        )


async def delete_test_case_sets(
    conn: TBConnection,
    project_key: str,
    created: list[CreatedTestCaseSet],
    user_key: str,
) -> None:
    """Delete the test case sets the agent created, newest first, as far as possible.

    TestBench deletes a set only while the caller holds the lock on it (and on the
    parent theme, which the run holds until the end), so each set is locked first.
    A set that cannot be deleted is logged and left; the others are still tried.

    Args:
        conn: The active TestBench connection.
        project_key: Key of the project owning the sets.
        created: The sets to delete.
        user_key: The triggering user, who takes the lock.
    """
    for test_case_set in reversed(created):
        try:
            await patch_test_structure_element_spec(
                conn,
                project_key,
                test_case_set.spec_key,
                SpecificationDetailsForUpdate(locker=OptionalUser(optional=user_key)),
            )
            await asyncio.to_thread(delete_test_case_set, conn, project_key, test_case_set.key)
        except Exception as error:
            logger.error(
                "Could not delete the created test case set '%s': %r", test_case_set.key, error
            )
