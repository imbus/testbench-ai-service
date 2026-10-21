"""Which projects a console user may edit.

A global TestBench administrator may edit everything. A ProjectAdministrator
may edit only the projects in which they are also TestManager -- that
combination is what TestBench itself treats as "manages this project".
"""

from typing import Any

from fastapi import HTTPException, status
from testbench_cli_reporter.testbench import Connection as TBConnection

from testbench_ai_service.log import logger
from testbench_ai_service.models.testbench import ProjectMember
from testbench_ai_service.utils.testbench import get_own_project_memberships
from testbench_ai_service.webui.paths import split_path
from testbench_ai_service.webui.session import Session

PROJECT_ADMIN_ROLE = "ProjectAdministrator"
PROJECT_MANAGER_ROLE = "TestManager"

# llm_config fields a project admin may not set. They decide which code the
# service imports or which endpoint receives the credentials, so they stay with
# the global administrator -- as does selecting the "custom" provider.
BLOCKED_LLM_FIELDS = frozenset({"class_path", "azure_endpoint", "auth_method"})


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


def _llm_violation(rest: list[str], value: Any) -> bool:
    """Whether setting ``llm_config.<rest>`` to *value* touches a blocked field.

    ``rest`` is what follows ``llm_config`` in the path; empty means the whole
    table is being written, in which case *value* is its content.
    """
    if not rest:
        return isinstance(value, dict) and (
            bool(BLOCKED_LLM_FIELDS & value.keys()) or value.get("provider") == "custom"
        )
    if rest[0] in BLOCKED_LLM_FIELDS:
        return True
    return rest == ["provider"] and value == "custom"


def _value_violation(value: Any) -> bool:
    """Whether a table written as a value carries a forbidden ``llm_config``.

    A path may stop above ``llm_config`` and hand over a nested dict instead,
    so the same rules must hold for every ``llm_config`` inside it.
    """
    if not isinstance(value, dict):
        return False
    return any(
        _llm_violation([], v) if k == "llm_config" else _value_violation(v)
        for k, v in value.items()
    )


def check_config_edits(session: Session, edits: dict[str, Any]) -> None:
    """Refuse (403) edits a non-admin may not make; the admin is never checked.

    A project admin may only touch ``projects."<name>"`` for a project they
    manage, and never the blocked ``llm_config`` fields. The whole batch is
    checked before anything is planned, so one forbidden path refuses all of it.
    Paths must already be well formed (``validate_edit_paths``).
    """
    if session.is_admin:
        return
    for path, value in edits.items():
        segments = split_path(path)
        allowed = (
            segments[0] == "projects" and len(segments) > 1 and can_manage(session, segments[1])
        )
        if allowed:
            tail = segments[2:]
            if "llm_config" in tail:
                allowed = not _llm_violation(tail[tail.index("llm_config") + 1 :], value)
            else:
                allowed = not _value_violation(value)
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Not allowed to change {path!r}",
            )
