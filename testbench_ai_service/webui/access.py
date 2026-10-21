"""Which projects a console user may edit.

A global TestBench administrator may edit everything. A ProjectAdministrator
may edit only the projects in which they are also TestManager -- that
combination is what TestBench itself treats as "manages this project".
"""

from testbench_cli_reporter.testbench import Connection as TBConnection

from testbench_ai_service.log import logger
from testbench_ai_service.models.testbench import ProjectMember
from testbench_ai_service.utils.testbench import get_own_project_memberships
from testbench_ai_service.webui.session import Session

PROJECT_ADMIN_ROLE = "ProjectAdministrator"
PROJECT_MANAGER_ROLE = "TestManager"


def managed_projects_from(
    global_roles: list[str], memberships: list[ProjectMember]
) -> frozenset[str]:
    """Names of the projects this user manages.

    Names, not keys, because ``config.toml`` keys its ``[projects."<name>"]``
    blocks by project name. Without the global role a TestManager membership
    grants nothing here.
    """
    if PROJECT_ADMIN_ROLE not in global_roles:
        return frozenset()
    return frozenset(
        m.projectName for m in memberships if PROJECT_MANAGER_ROLE in [r.value for r in m.roles]
    )


def read_managed_projects(conn: TBConnection, global_roles: list[str]) -> frozenset[str]:
    """Read the managed projects over the login connection; never raises.

    Like the project list and user key, this must not be able to fail the
    login: the user then simply manages nothing.
    """
    if PROJECT_ADMIN_ROLE not in global_roles:
        return frozenset()
    try:
        memberships = get_own_project_memberships(conn)
    except Exception as e:  # any failure here only costs the project-admin rights
        logger.warning("Could not read the TestBench project memberships: %r", e)
        return frozenset()
    return managed_projects_from(global_roles, memberships)


def can_manage(session: Session, project: str | None) -> bool:
    """True when *session* may edit *project* (None: only a global admin may)."""
    if session.is_admin:
        return True
    if project is None:
        return False
    return project in session.managed_projects
