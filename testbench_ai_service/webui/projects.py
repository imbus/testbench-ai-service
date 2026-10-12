"""The console's TestBench project list.

Fetched **once**, inside the connection the login already has, and cached on the
session for its lifetime (design D3). The reason is not performance: on
TestBench 3 the stored ``tb_session_token`` *is* the operator's plaintext
password (see :mod:`~testbench_ai_service.webui.session`), so every additional
outbound call is another use of a credential the console would rather not touch.
``POST /projects/refresh`` exists for the operator who added a project since
signing in.

Nothing in this module raises. A TestBench that cannot answer must not be able
to fail a login, nor a config edit that has nothing to do with projects
(design D4): every failure comes back as an ``error`` string on
:class:`ProjectFetch`, and the console surfaces it next to an empty list.
"""

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from testbench_cli_reporter.testbench import Connection as TBConnection

from testbench_ai_service.config import AppConfig
from testbench_ai_service.log import logger
from testbench_ai_service.transport import (
    DEFAULT_CONNECT_TIMEOUT,
    DEFAULT_READ_TIMEOUT,
    harden_connection,
)
from testbench_ai_service.webui.models import ProjectRef, ProjectsResponse
from testbench_ai_service.webui.session import Session


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


def fetch_projects_with_token(config: AppConfig, token: str) -> ProjectFetch:
    """Open a short-lived connection from the stored token and fetch. Never raises.

    Used only by ``POST /projects/refresh``; the login path calls
    :func:`fetch_projects` on the connection it already has instead of opening a
    second one.
    """
    try:
        conn = TBConnection(
            config.tb_server_url,
            verify=config.tb_ssl_ca_bundle or config.tb_ssl_verify,
            sessionToken=token,
            connection_timeout_sec=math.ceil(DEFAULT_READ_TIMEOUT),
        )
    except ValueError as e:
        # TBConnection validates the URL shape in its constructor, and only
        # there. A misconfigured tb_server_url is the operator's problem to fix
        # in the Service form -- it is not a reason to fail the request they
        # actually made.
        logger.error("Cannot reach TestBench to list projects: %s", e)
        return ProjectFetch(projects=[], fetched_at=_now(), error=str(e))

    try:
        # harden_connection reads conn.session, which is what completes the
        # vendored client's lazy setup -- server version, authentication,
        # heartbeat. An unreachable server or a token TestBench no longer
        # accepts fails here, not in get_all_projects, so this needs the same
        # catch fetch_projects has rather than propagating into a 500.
        harden_connection(
            conn,
            connect_timeout=DEFAULT_CONNECT_TIMEOUT,
            read_timeout=DEFAULT_READ_TIMEOUT,
        )
    except Exception as e:  # see fetch_projects: a narrower tuple would not hold
        logger.warning("Could not open a TestBench connection to list projects: %s", e)
        conn.close()
        return ProjectFetch(projects=[], fetched_at=_now(), error=str(e) or type(e).__name__)

    try:
        return fetch_projects(conn)
    finally:
        conn.close()


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
