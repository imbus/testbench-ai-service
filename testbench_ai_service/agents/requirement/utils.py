import asyncio
from collections import defaultdict
from http import HTTPStatus
from pathlib import Path

import requests
from fastapi import HTTPException, status
from pydantic import ValidationError
from requests.auth import HTTPBasicAuth
from testbench_cli_reporter.testbench import Connection as TBConnection

from testbench_ai_service.agents.requirement.model import (
    ExtendedRequirement,
    RequirementAgentArgs,
)
from testbench_ai_service.exceptions import TRANSPORT_ERRORS
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
    get_tov_baselines,
    patch_test_structure_element_spec,
)
from testbench_ai_service.utils.time_utils import current_time

#: Agent key used to resolve this agent's write-back templates.
AGENT_KEY = "requirement"

#: Timeout (connect, read) in seconds for calls to the RM service.
RM_REQUEST_TIMEOUT_SEC = (10, 60)


async def load_requirements(
    conn: TBConnection,
    rm_service: RequirementAgentArgs,
    project_key: str,
    root_uid: str,
    tov_key: str,
    cycle_key: str | None = None,
    filtering: FilteringOptions | None = None,
) -> list[ExtendedRequirement]:
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
    requirements = await asyncio.to_thread(
        get_requirements,
        conn,
        project_key,
        root_uid,
        tov_key,
        cycle_key=cycle_key,
        filtering=filtering,
    )

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

    extended_requirements: list[ExtendedRequirement] = []
    for requirement in requirements:
        baseline, extended = await _find_extended_requirement(
            baselines_by_repo.get(requirement.repositoryId, []), requirement, rm_service
        )
        if baseline is None or extended is None:
            logger.warning(
                "Requirement '%s' (version '%s') was not found in any baseline of repository "
                "'%s'; continuing with its TOV data only",
                requirement.id,
                requirement.version,
                requirement.repositoryId,
            )
            extended = ExtendedRequirement.from_assignment(requirement)
        else:
            logger.debug(
                "Requirement '%s' resolved to baseline '%s'",
                requirement.id,
                _baseline_name(baseline),
            )
        extended_requirements.append(extended)

    return extended_requirements


def _baseline_name(baseline: dict) -> str:
    """Return a baseline's display name, e.g. ``Current Baseline (Dream Car (DCS))``."""
    return f"{baseline['name']} ({baseline['reqProjectName']})"


async def _find_extended_requirement(
    baselines: list[dict],
    requirement: RequirementAssignment,
    rm_service: RequirementAgentArgs,
) -> tuple[dict | None, ExtendedRequirement | None]:
    """Find the baseline a requirement belongs to by asking each candidate in turn.

    The requirement assignment only names its repository, so when a repository has
    several baselines in the TOV the first baseline that knows the requirement wins.

    Returns:
        The matching baseline key and the requirement's extended data, or
        ``(None, None)`` when no candidate baseline contains the requirement.
    """
    for baseline in baselines:
        extended = await asyncio.to_thread(
            get_extended_requirement,
            rm_service,
            baseline["reqProjectName"],
            baseline["name"],
            requirement.id,
            requirement.version,
        )
        if extended is not None:
            return baseline, extended
    return None, None


def get_extended_requirement(
    rm_service: RequirementAgentArgs,
    req_project: str,
    baseline: str,
    requirement_id: str,
    version: str,
) -> ExtendedRequirement | None:
    """Fetch a requirement's extended data from a baseline of the RM service.

    Returns:
        The extended requirement, or ``None`` when the baseline does not contain it
        (the RM service answers ``400`` for an unknown project and ``404`` for an
        unknown baseline or requirement).

    Raises:
        HTTPException: ``502`` when the RM service is unreachable, answers with any
            other error status, or returns a body that is not an extended requirement.
    """
    url = f"{rm_service.rm_service_url}projects/{req_project}/baselines/{baseline}/extended-requirement"
    body = {"id": requirement_id, "version": version}
    try:
        response = requests.post(
            url,
            json=body,
            auth=HTTPBasicAuth(rm_service.rm_username, rm_service.rm_password),
            timeout=RM_REQUEST_TIMEOUT_SEC,
        )
    except TRANSPORT_ERRORS as e:
        detail = f"Could not reach RM service at '{url}': {e!s}"
        logger.error(detail)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail) from e

    if response.status_code in (HTTPStatus.BAD_REQUEST, HTTPStatus.NOT_FOUND):
        logger.warning(
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
