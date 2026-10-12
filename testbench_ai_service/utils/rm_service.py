"""Requirement details from the RM service, shared by the requirement-based agents.

A requirement assignment from the TOV names a requirement but carries no description.
The description comes from the RM service's ``extended-requirement`` endpoint, asked
in the baselines the TOV is assigned to. The RM project is taken from each baseline,
so no mapping from TestBench project to RM project is configured anywhere.
"""

import asyncio
from collections import defaultdict
from http import HTTPStatus
from typing import Self

import requests
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from requests.auth import HTTPBasicAuth
from testbench_cli_reporter.testbench import Connection as TBConnection

from testbench_ai_service.log import logger
from testbench_ai_service.models.agent import AgentArgs
from testbench_ai_service.models.testbench import RequirementAssignment
from testbench_ai_service.transport import (
    DEFAULT_MAX_RETRIES,
    ResilientHTTPAdapter,
    build_retry,
)
from testbench_ai_service.utils.testbench import get_tov_baselines

#: Timeout (connect, read) in seconds for calls to the RM service.
RM_REQUEST_TIMEOUT_SEC = (10, 60)

#: Upper bound on the requests to the RM service in flight at once.
RM_MAX_CONCURRENT_REQUESTS = 8


class RmServiceArgs(AgentArgs):
    """Agent args giving access to the RM service; agents that read requirements extend it."""

    rm_service_url: str | None = Field(
        default=None,
        description="RM service to fetch requirement details from. Unset means TOV data only.",
    )
    rm_username: str | None = None
    rm_password: str | None = None

    @field_validator("rm_service_url", mode="after")
    @classmethod
    def ensure_trailing_slash(cls, rm_service_url: str | None) -> str | None:
        """Append a trailing slash so paths can be joined onto the URL directly."""
        if rm_service_url is None or rm_service_url.endswith("/"):
            return rm_service_url
        return f"{rm_service_url}/"

    @model_validator(mode="after")
    def require_rm_credentials(self) -> Self:
        """Reject an RM service URL configured without the credentials to call it."""
        if self.rm_service_url is not None and (
            self.rm_username is None or self.rm_password is None
        ):
            raise ValueError("rm_service_url requires rm_username and rm_password")
        return self


class Requirement(BaseModel):
    """A requirement as the model sees it: its TOV assignment merged with its RM details."""

    #: TestBench key, which test case sets reference the requirement by.
    key: str
    version: str
    title: str
    description: str | None
    status: str | None
    priority: str | None
    owner: str | None
    documents: list[str]
    external_ref: str | None

    @classmethod
    def from_details(
        cls, assignment: RequirementAssignment, extended: "ExtendedRequirement"
    ) -> "Requirement":
        """Merge a requirement's TOV assignment with its extended data."""
        return cls(
            key=assignment.key,
            version=extended.key.version,
            title=extended.name,
            description=extended.description,
            status=extended.status or None,
            priority=extended.priority or None,
            owner=extended.owner or None,
            documents=extended.documents or [],
            external_ref=extended.extendedId or None,
        )


class ExtendedRequirementKey(BaseModel):
    id: str
    version: str


class ExtendedRequirement(BaseModel):
    """A requirement as returned by the RM service's ``extended-requirement`` endpoint."""

    model_config = ConfigDict(populate_by_name=True)
    name: str
    extendedId: str = Field(alias="extendedID")
    key: ExtendedRequirementKey
    owner: str
    status: str
    priority: str
    requirement: bool
    description: str | None
    documents: list[str] | None
    baseline: str | None

    @classmethod
    def from_assignment(cls, assignment: RequirementAssignment) -> "ExtendedRequirement":
        """Build a fallback from the TOV's requirement data alone, without RM details."""
        return cls(
            name=assignment.name,
            extendedId=assignment.extendedId,
            key=ExtendedRequirementKey(id=assignment.id, version=assignment.version),
            owner=assignment.owner,
            status=assignment.status,
            priority=assignment.priority,
            requirement=True,
            description=None,
            documents=None,
            baseline=None,
        )


async def fetch_requirement_details(
    conn: TBConnection,
    rm_service: RmServiceArgs,
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


def _rm_session(rm_service: RmServiceArgs) -> requests.Session:
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

    Never raises: the RM details are optional, so any failure is logged and treated
    as a miss, and the caller falls back to the requirement's TOV data (without
    description and documents). A plain miss is logged at debug level only: with
    several baselines per repository misses are expected, and the caller warns once
    if no baseline has the requirement.

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
        unknown baseline or requirement), the RM service is unreachable, answers with
        any other error status, or returns a body that is not an extended requirement.
    """
    url = f"{rm_service_url}projects/{req_project}/baselines/{baseline}/extended-requirement"
    body = {"id": requirement_id, "version": version}
    try:
        response = session.post(url, json=body)
    except requests.exceptions.RequestException as e:
        logger.warning("Could not reach RM service at '%s': %s", url, e)
        return None

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
    except requests.exceptions.HTTPError:
        logger.warning(
            "RM service error %s for '%s': %s", response.status_code, url, response.text.strip()
        )
        return None

    try:
        return ExtendedRequirement.model_validate(response.json())
    except (ValueError, ValidationError) as e:
        logger.warning("Invalid extended requirement returned by RM service for '%s': %s", url, e)
        return None
