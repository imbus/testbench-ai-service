import asyncio
from collections import defaultdict
from http import HTTPStatus
from pathlib import Path

import requests
from fastapi import HTTPException, status
from pydantic import ValidationError
from requests.auth import HTTPBasicAuth
from testbench_cli_reporter.testbench import Connection as TBConnection

from testbench_ai_service.agents.requirement.context import html_text
from testbench_ai_service.agents.requirement.model import (
    ExistingTestCaseSet,
    ExtendedRequirement,
    Requirement,
    RequirementAgentArgs,
    Theme,
    ThemeContext,
)
from testbench_ai_service.exceptions import TRANSPORT_ERRORS
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
from testbench_ai_service.transport import (
    DEFAULT_MAX_RETRIES,
    ResilientHTTPAdapter,
    build_retry,
)
from testbench_ai_service.utils.html_utils import escape_html, has_visible_text
from testbench_ai_service.utils.template_utils import render_template, resolve_template_path
from testbench_ai_service.utils.testbench import (
    get_requirements,
    get_test_case_set_details,
    get_test_theme_details,
    get_tov_baselines,
    patch_test_structure_element_spec,
)
from testbench_ai_service.utils.time_utils import current_time

#: Agent key used to resolve this agent's write-back templates.
AGENT_KEY = "requirement"

#: Timeout (connect, read) in seconds for calls to the RM service.
RM_REQUEST_TIMEOUT_SEC = (10, 60)

#: Upper bound on the requests to the RM service in flight at once.
RM_MAX_CONCURRENT_REQUESTS = 8

#: Upper bound on the requests to TestBench in flight at once.
TB_MAX_CONCURRENT_REQUESTS = 4

#: Length a test case set's description is cut to in the prompt.
DESCRIPTION_SHORT_MAX_CHARS = 300


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


async def fetch_requirement_details(
    conn: TBConnection,
    rm_service: RequirementAgentArgs,
    tov_key: str,
    requirements: list[RequirementAssignment],
) -> list[ExtendedRequirement]:
    """Look up each requirement's details in the RM service.

    A requirement that no baseline of its repository contains keeps its TOV data
    only. Without a configured ``rm_service_url`` every requirement does.

    Args:
        conn: The active TestBench connection.
        rm_service: The agent args holding the RM service URL and credentials.
        tov_key: Key of the TOV whose baselines are searched.
        requirements: The requirements loaded from the TOV.

    Returns:
        One extended requirement per entry of ``requirements``, in the same order.
    """
    if rm_service.rm_service_url is None:
        logger.debug("No rm_service_url configured; using the TOV requirement data only")
        return [ExtendedRequirement.from_assignment(requirement) for requirement in requirements]

    baselines_by_repo: dict[str, list[dict]] = defaultdict(list)
    for baseline in await asyncio.to_thread(get_tov_baselines, conn, tov_key):
        baselines_by_repo[baseline["repository"]].append(baseline)

    for repository, baselines in baselines_by_repo.items():
        if len(baselines) > 1:
            logger.warning(
                "Repository '%s' has %d baselines in TOV '%s': %s",
                repository,
                len(baselines),
                tov_key,
                [_baseline_name(baseline) for baseline in baselines],
            )

    # One pooled session for all lookups; the semaphore caps the requests in flight.
    semaphore = asyncio.Semaphore(RM_MAX_CONCURRENT_REQUESTS)
    with _rm_session(rm_service) as session:
        tasks = [
            asyncio.create_task(
                _resolve_requirement(
                    session,
                    semaphore,
                    rm_service.rm_service_url,
                    baselines_by_repo.get(requirement.repositoryId, []),
                    requirement,
                )
            )
            for requirement in requirements
        ]
        try:
            return list(await asyncio.gather(*tasks))
        except BaseException:
            # Stop the lookups not yet started instead of letting them run on unobserved.
            for task in tasks:
                task.cancel()
            raise


def _rm_session(rm_service: RequirementAgentArgs) -> requests.Session:
    """Create a session authenticated against the RM service, pooled for concurrent use."""
    session = requests.Session()
    session.auth = HTTPBasicAuth(rm_service.rm_username, rm_service.rm_password)
    adapter = ResilientHTTPAdapter(
        timeout=RM_REQUEST_TIMEOUT_SEC,
        max_retries=build_retry(DEFAULT_MAX_RETRIES),
        pool_maxsize=RM_MAX_CONCURRENT_REQUESTS,
    )
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def _baseline_name(baseline: dict) -> str:
    """Return a baseline's display name, e.g. ``Current Baseline (Dream Car (DCS))``."""
    return f"{baseline['name']} ({baseline['reqProjectName']})"


async def _resolve_requirement(
    session: requests.Session,
    semaphore: asyncio.Semaphore,
    rm_service_url: str,
    baselines: list[dict],
    requirement: RequirementAssignment,
) -> ExtendedRequirement:
    """Resolve a requirement's extended data, falling back to its TOV data.

    The requirement assignment only names its repository, so when a repository has
    several baselines in the TOV they are asked in turn and the first baseline that
    knows the requirement wins.

    Returns:
        The requirement's extended data from the RM service, or one built from its
        TOV data alone when no candidate baseline contains it.
    """
    for baseline in baselines:
        async with semaphore:
            extended = await asyncio.to_thread(
                get_extended_requirement,
                session,
                rm_service_url,
                baseline["reqProjectName"],
                baseline["name"],
                requirement.id,
                requirement.version,
            )
        if extended is not None:
            logger.debug(
                "Requirement '%s' resolved to baseline '%s'",
                requirement.id,
                _baseline_name(baseline),
            )
            return extended

    logger.warning(
        "Requirement '%s' (version '%s') was not found in any baseline of repository "
        "'%s'; continuing with its TOV data only",
        requirement.id,
        requirement.version,
        requirement.repositoryId,
    )
    return ExtendedRequirement.from_assignment(requirement)


def get_extended_requirement(
    session: requests.Session,
    rm_service_url: str,
    req_project: str,
    baseline: str,
    requirement_id: str,
    version: str,
) -> ExtendedRequirement | None:
    """Fetch a requirement's extended data from a baseline of the RM service.

    A miss is logged at debug level only: with several baselines per repository
    misses are expected, and the caller warns once if no baseline has the requirement.

    Args:
        session: Session authenticated against the RM service (see ``_rm_session``).
        rm_service_url: Base URL of the RM service, with a trailing slash.
        req_project: Name of the RM project the baseline belongs to.
        baseline: Name of the baseline to look in.
        requirement_id: ID of the requirement.
        version: Version of the requirement.

    Returns:
        The extended requirement, or ``None`` when the baseline does not contain it
        (the RM service answers ``400`` for an unknown project and ``404`` for an
        unknown baseline or requirement).

    Raises:
        HTTPException: ``502`` when the RM service is unreachable, answers with any
            other error status, or returns a body that is not an extended requirement.
    """
    url = f"{rm_service_url}projects/{req_project}/baselines/{baseline}/extended-requirement"
    body = {"id": requirement_id, "version": version}
    try:
        response = session.post(url, json=body)
    except TRANSPORT_ERRORS as e:
        detail = f"Could not reach RM service at '{url}': {e!s}"
        logger.error(detail)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail) from e

    if response.status_code in (HTTPStatus.BAD_REQUEST, HTTPStatus.NOT_FOUND):
        logger.debug(
            "Requirement '%s' (version '%s') not found in project '%s', baseline '%s': %s - %s",
            requirement_id,
            version,
            req_project,
            baseline,
            response.status_code,
            response.text.strip(),
        )
        return None

    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as e:
        detail = f"RM service error {response.status_code} for '{url}': {response.text.strip()}"
        logger.error(detail)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail) from e

    try:
        return ExtendedRequirement.model_validate(response.json())
    except (ValueError, ValidationError) as e:
        detail = f"Invalid extended requirement returned by RM service for '{url}': {e!s}"
        logger.error(detail)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail) from e


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
