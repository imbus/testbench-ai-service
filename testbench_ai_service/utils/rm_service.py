"""Requirement details from the RM service, shared by the requirement-based agents.

A requirement assignment from the TOV names a requirement but carries no description.
The description comes from the RM service's ``extended-requirement`` endpoint, asked
in the baselines the TOV is assigned to. The RM project is taken from each baseline,
so no mapping from TestBench project to RM project is configured anywhere.

TestBench lists a TOV's baselines only on its legacy API, which a JWT cannot use. With
a JWT, or if that lookup fails, the RM service's own baselines are searched instead:
those of ``rm_projects``, or of every RM project.
"""

import asyncio
from collections import defaultdict
from http import HTTPStatus
from typing import Any, Self

import requests
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from requests.auth import HTTPBasicAuth
from testbench_cli_reporter.testbench import Connection as TBConnection

from testbench_ai_service.auth import is_jwt
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

#: Failures of listing the RM service's projects or baselines: transport and HTTP
#: errors, and bodies that are not JSON or not shaped as expected.
RM_LISTING_ERRORS = (
    requests.exceptions.RequestException,
    ValueError,
    KeyError,
    TypeError,
    AttributeError,
)


class RmServiceArgs(AgentArgs):
    """Agent args giving access to the RM service; agents that read requirements extend it."""

    rm_service_url: str | None = Field(
        default=None,
        description="RM service to fetch requirement details from. Unset means TOV data only.",
    )
    rm_username: str | None = None
    rm_password: str | None = None
    rm_projects: list[str] | None = Field(
        default=None,
        min_length=1,
        description=(
            "RM projects searched, in this order, when TestBench cannot name the TOV's "
            "baselines (e.g. with a JWT). Unset means every project of the RM service."
        ),
    )

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
        return cls.from_rm(assignment.key, extended)

    @classmethod
    def from_rm(cls, key: str, extended: "ExtendedRequirement") -> "Requirement":
        """A requirement from its extended data, referenced by ``key`` in TestBench."""
        return cls(
            key=key,
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

    The baselines to search come from the TOV. When TestBench cannot name them (its
    baseline lookup needs the legacy API, which a JWT cannot use), the baselines of the
    RM projects in ``rm_projects`` - or of every RM project - are searched instead.

    A requirement that no candidate baseline contains keeps its TOV data only.
    Without a configured ``rm_service_url`` every requirement does.

    Args:
        conn: The active TestBench connection.
        rm_service: The agent args holding the RM service URL, credentials and projects.
        tov_key: Key of the TOV whose baselines are searched.
        requirements: The requirements loaded from the TOV.

    Returns:
        One extended requirement per entry of ``requirements``, in the same order.
    """
    if rm_service.rm_service_url is None:
        logger.debug("No rm_service_url configured; using the TOV requirement data only")
        return [ExtendedRequirement.from_assignment(requirement) for requirement in requirements]

    tov_baselines = await _load_tov_baselines(conn, tov_key)

    # One pooled session for all lookups; the semaphore caps the requests in flight.
    semaphore = asyncio.Semaphore(RM_MAX_CONCURRENT_REQUESTS)
    with _rm_session(rm_service) as session:
        if tov_baselines is None:
            rm_baselines = await asyncio.to_thread(
                discover_rm_baselines, session, rm_service.rm_service_url, rm_service.rm_projects
            )
            candidates = {requirement.repositoryId: rm_baselines for requirement in requirements}
        else:
            candidates = _baselines_by_repository(tov_baselines, tov_key)
        tasks = [
            asyncio.create_task(
                _resolve_requirement(
                    session,
                    semaphore,
                    rm_service.rm_service_url,
                    candidates.get(requirement.repositoryId, []),
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


async def _load_tov_baselines(conn: TBConnection, tov_key: str) -> list[dict] | None:
    """Return the TOV's requirement baselines, or ``None`` when TestBench cannot name them.

    TestBench lists a TOV's baselines only on its legacy API, which a JWT cannot
    authenticate against, so a JWT connection skips the lookup instead of failing on it.
    """
    if isinstance(conn.session_token, str) and is_jwt(conn.session_token):
        logger.info(
            "TOV baselines are not available with a JWT; searching the RM service's baselines"
        )
        return None
    try:
        return await asyncio.to_thread(get_tov_baselines, conn, tov_key)
    except (requests.exceptions.RequestException, ValueError, KeyError, TypeError) as e:
        logger.warning(
            "Could not load the baselines of TOV '%s' from TestBench (%s); "
            "searching the RM service's baselines",
            tov_key,
            e,
        )
        return None


def _baselines_by_repository(baselines: list[dict], tov_key: str) -> dict[str, list[dict]]:
    """Group the TOV's baselines by the repository they belong to."""
    baselines_by_repo: dict[str, list[dict]] = defaultdict(list)
    for baseline in baselines:
        baselines_by_repo[baseline["repository"]].append(baseline)

    for repository, repo_baselines in baselines_by_repo.items():
        if len(repo_baselines) > 1:
            logger.warning(
                "Repository '%s' has %d baselines in TOV '%s': %s",
                repository,
                len(repo_baselines),
                tov_key,
                [_baseline_name(baseline) for baseline in repo_baselines],
            )
    return baselines_by_repo


async def find_rm_requirement(
    conn: TBConnection, rm_service: RmServiceArgs, tov_key: str, ids: list[str]
) -> ExtendedRequirement | None:
    """Look a requirement up in the RM service by its ID alone.

    For a requirement that is not assigned in the TOV, TestBench names neither its
    repository nor its version. So each candidate ID is asked for its versions in the
    TOV's baselines (or, when TestBench cannot name them, in the RM service's
    baselines) in turn, and the latest version of the first hit is read. Loading whole
    requirement trees instead takes minutes on large baselines.

    Args:
        conn: The active TestBench connection.
        rm_service: The agent args holding the RM service URL, credentials and projects.
        tov_key: Key of the TOV whose baselines are searched.
        ids: The values the requirement may be known by, from the trigger.

    Returns:
        The requirement's extended data, or ``None`` when no RM service is configured,
        it cannot be reached, or no baseline knows a requirement with one of ``ids``.
    """
    if rm_service.rm_service_url is None or not ids:
        return None
    rm_service_url = rm_service.rm_service_url
    tov_baselines = await _load_tov_baselines(conn, tov_key)
    with _rm_session(rm_service) as session:
        if tov_baselines is None:
            baselines = await asyncio.to_thread(
                discover_rm_baselines, session, rm_service_url, rm_service.rm_projects
            )
        else:
            baselines = tov_baselines
        for baseline in baselines:
            for requirement_id in ids:
                version = await asyncio.to_thread(
                    get_latest_requirement_version,
                    session,
                    rm_service_url,
                    baseline["reqProjectName"],
                    baseline["name"],
                    requirement_id,
                )
                if version is None:
                    continue
                logger.debug(
                    "Requirement '%s' found in baseline '%s' with version '%s'",
                    requirement_id,
                    _baseline_name(baseline),
                    version,
                )
                return await asyncio.to_thread(
                    get_extended_requirement,
                    session,
                    rm_service_url,
                    baseline["reqProjectName"],
                    baseline["name"],
                    requirement_id,
                    version,
                )
    logger.warning("Requirement %s was not found in any RM baseline of TOV '%s'", ids, tov_key)
    return None


#: Placeholder version for asking a requirement's versions: the RM service requires
#: one in the key, but every reader looks the versions up by the ID alone.
_ANY_VERSION = "*"


def get_latest_requirement_version(
    session: requests.Session,
    rm_service_url: str,
    req_project: str,
    baseline: str,
    requirement_id: str,
) -> str | None:
    """The name of a requirement's latest version in a baseline of the RM service.

    Never raises, like ``get_extended_requirement``: an unknown requirement, an
    unreachable RM service or an unexpected body all count as a miss.

    Returns:
        The version name, or ``None`` when the baseline does not know the requirement.
    """
    url = f"{rm_service_url}projects/{req_project}/baselines/{baseline}/requirement-versions"
    try:
        response = session.post(url, json={"id": requirement_id, "version": _ANY_VERSION})
    except requests.exceptions.RequestException as e:
        logger.warning("Could not reach RM service at '%s': %s", url, e)
        return None
    if response.status_code in (HTTPStatus.BAD_REQUEST, HTTPStatus.NOT_FOUND):
        logger.debug(
            "Requirement '%s' not found in project '%s', baseline '%s': %s",
            requirement_id,
            req_project,
            baseline,
            response.status_code,
        )
        return None
    try:
        response.raise_for_status()
        versions = response.json()
        return max(versions, key=lambda version: version["date"])["name"] if versions else None
    except (requests.exceptions.HTTPError, *RM_LISTING_ERRORS) as e:
        logger.warning(
            "Could not read the versions of requirement '%s' at '%s': %s", requirement_id, url, e
        )
        return None


def discover_rm_baselines(
    session: requests.Session, rm_service_url: str, rm_projects: list[str] | None
) -> list[dict]:
    """List the baselines of the RM projects to search, in the order they are tried.

    Projects are searched in the order of ``rm_projects``, or of the RM service when
    unset. Within a project its ``CURRENT`` baseline comes first. Never raises: a
    project whose baselines cannot be listed is skipped, and an RM service that cannot
    list its projects yields no baselines.

    Args:
        session: Session authenticated against the RM service (see ``_rm_session``).
        rm_service_url: Base URL of the RM service, with a trailing slash.
        rm_projects: Names of the RM projects to search, or ``None`` for all of them.

    Returns:
        Baselines shaped like the TOV's (``name`` and ``reqProjectName``).
    """
    if rm_projects is None:
        try:
            rm_projects = [
                str(project) for project in _get_json(session, f"{rm_service_url}projects")
            ]
        except RM_LISTING_ERRORS as e:
            logger.warning("Could not list the projects of the RM service: %s", e)
            return []

    baselines: list[dict] = []
    for project in rm_projects:
        url = f"{rm_service_url}projects/{project}/baselines"
        try:
            project_baselines = [
                {"name": baseline["name"], "reqProjectName": project, "type": baseline.get("type")}
                for baseline in _get_json(session, url)
            ]
        except RM_LISTING_ERRORS as e:
            logger.warning("Could not list the baselines of RM project '%s': %s", project, e)
            continue
        # A project's current baseline is the likeliest to hold the TOV's requirement versions.
        baselines.extend(
            sorted(project_baselines, key=lambda baseline: baseline["type"] != "CURRENT")
        )

    logger.debug(
        "Searching %d RM baselines: %s",
        len(baselines),
        [_baseline_name(baseline) for baseline in baselines],
    )
    return baselines


def _get_json(session: requests.Session, url: str) -> Any:
    """GET ``url`` and return its JSON body, raising on an error status."""
    response = session.get(url)
    response.raise_for_status()
    return response.json()


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
