"""The console's TestBench project list.

Fetched **once**, inside the connection the login already has, and cached on the
session for its lifetime (design D3), so page loads never cost a TestBench
round-trip. ``POST /projects/refresh`` exists for the operator who added a
project since signing in; it reuses the session's live connection (see
:mod:`~testbench_ai_service.webui.tb_link`).

Nothing in this module raises. A TestBench that cannot answer must not be able
to fail a login, nor a config edit that has nothing to do with projects
(design D4): every failure comes back as an ``error`` string on
:class:`ProjectFetch`, and the console surfaces it next to an empty list.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

from testbench_ai_service.log import logger
from testbench_ai_service.webui.models import ProjectRef, ProjectsResponse
from testbench_ai_service.webui.session import Session
from testbench_ai_service.webui.tb_link import TestBenchLink


@dataclass(frozen=True)
class ProjectFetch:
    """One attempt at reading the project list.

    ``error`` is ``None`` only when the list is genuinely TestBench's answer.
    ``fetched_at`` is set either way: "we tried at 14:02 and it failed" is
    something the console has to be able to show.
    """

    projects: list[ProjectRef]
    fetched_at: datetime
    error: str | None = None


def parse_projects(payload: Any) -> list[ProjectRef]:
    """The ``{name, key}`` pairs in a ``get_all_projects()`` payload.

    Deliberately forgiving about everything else. The payload is asked for with
    ``includeTOVs``/``includeCycles``, so each entry carries a whole test-object
    tree that has no business on a session, and the vendored client does no
    validation of its own -- a shape this function did not expect must cost the
    operator the odd project row, never the login.
    """
    if not isinstance(payload, dict):
        logger.warning("TestBench project list was not a mapping: %s", type(payload).__name__)
        return []
    entries = payload.get("projects")
    if not isinstance(entries, list):
        logger.warning("TestBench project list carried no 'projects' array")
        return []

    refs: list[ProjectRef] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        key = entry.get("key")
        if not isinstance(name, str) or not name or key is None:
            # A project with no name cannot key a [projects."<name>"] block, so
            # it is not addressable by anything the console can write.
            continue
        refs.append(ProjectRef(name=name, key=str(key)))
    return refs


def _now() -> datetime:
    return datetime.now(timezone.utc)


def fetch_projects(conn: Any) -> ProjectFetch:
    """Read the project list from an already-authenticated *conn*. Never raises.

    Catches ``Exception`` rather than a curated tuple on purpose: the vendored
    client indexes into its own JSON responses without checking
    (``all_projects["projects"].sort(...)``), so a TestBench that answers an
    unexpected shape raises ``KeyError`` or ``TypeError`` from inside the
    library. Letting that class of failure through would mean an unrelated
    TestBench quirk 500s the login.
    """
    try:
        payload = conn.get_all_projects()
    except Exception as e:  # see docstring: a narrower tuple would not hold
        logger.warning("Could not read the TestBench project list: %s", e)
        return ProjectFetch(projects=[], fetched_at=_now(), error=str(e) or type(e).__name__)
    return ProjectFetch(projects=parse_projects(payload), fetched_at=_now())


def fetch_projects_via_link(link: TestBenchLink | None) -> ProjectFetch:
    """Fetch over the session's live connection. Never raises.

    Used only by ``POST /projects/refresh``. The link renews the TestBench
    session if it has ended -- by the heartbeat's 401, or a 401 on this very
    call -- so a refresh long after the five-minute token lifetime still works.
    A renewal that fails (TestBench down, password changed) is reported like
    any other failed fetch.
    """
    if link is None:
        return ProjectFetch(projects=[], fetched_at=_now(), error="No TestBench connection")
    try:
        payload = link.call(lambda conn: conn.get_all_projects())
    except HTTPException as e:
        logger.warning("Could not renew the TestBench session to list projects: %s", e.detail)
        return ProjectFetch(projects=[], fetched_at=_now(), error=str(e.detail))
    except Exception as e:  # see fetch_projects: a narrower tuple would not hold
        logger.warning("Could not read the TestBench project list: %s", e)
        return ProjectFetch(projects=[], fetched_at=_now(), error=str(e) or type(e).__name__)
    return ProjectFetch(projects=parse_projects(payload), fetched_at=_now())


def record_projects(session: Session, fetch: ProjectFetch) -> None:
    """Cache *fetch* on *session*.

    A **failed** fetch updates the timestamp and the error but keeps whatever
    list the session already had: a refresh that timed out is no reason to take
    the operator's project columns away, and the ``error`` plus the new
    ``fetched_at`` already say the list may be stale.
    """
    session.projects_fetched_at = fetch.fetched_at
    session.projects_error = fetch.error
    if fetch.error is None:
        session.projects = list(fetch.projects)


def projects_response(session: Session) -> ProjectsResponse:
    """The session's cached list, as the API reports it.

    ``source`` is ``"unavailable"`` both when a fetch failed and when none has
    happened at all. The console keys its "add a project by name" fallback off
    that value, so an empty list must never be presented as TestBench's own
    answer unless it really was one.
    """
    healthy = session.projects_error is None and session.projects_fetched_at is not None
    return ProjectsResponse(
        projects=list(session.projects),
        fetched_at=session.projects_fetched_at,
        source="testbench" if healthy else "unavailable",
        error=session.projects_error,
    )
