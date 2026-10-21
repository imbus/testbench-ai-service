"""Which projects a console user may edit.

A global TestBench administrator may edit everything. A ProjectAdministrator
may edit only the projects in which they are also TestManager -- that
combination is what TestBench itself treats as "manages this project".
"""

import re
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from fastapi import HTTPException, status
from testbench_cli_reporter.testbench import Connection as TBConnection

from testbench_ai_service.log import logger
from testbench_ai_service.models.testbench import ProjectMember
from testbench_ai_service.utils.testbench import get_own_project_memberships
from testbench_ai_service.webui.models import PromptUsage
from testbench_ai_service.webui.paths import split_path
from testbench_ai_service.webui.prompts import WritePlan, prompt_usages
from testbench_ai_service.webui.session import Session

PROJECT_ADMIN_ROLE = "ProjectAdministrator"
PROJECT_MANAGER_ROLE = "TestManager"

# A fork's directory is ``<agent>__<slug>``. A project admin may only edit
# directories that carry it, so a shared template can never qualify.
FORK_MARKER = "__"

# agents.<key>.prompt.file below a project: four segments.
_PROMPT_FILE_DEPTH = 4

# The only llm_config fields a project admin may set. An allow-list, because
# LLMConfig accepts arbitrary extras and any of them could steer which code is
# imported or where credentials are sent (class_path, azure_endpoint,
# auth_method, deployment_mapping, ...). Selecting the "custom" provider is
# refused separately.
ALLOWED_LLM_FIELDS = frozenset(
    {"provider", "model", "timeout", "max_retries", "api_version", "extra_models"}
)


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


def require_project_access(session: Session, project: str | None) -> None:
    """Refuse (403) a project-scoped action on a project *session* may not manage.

    Without a project only a global admin passes: a project admin's rights exist
    per project, so an unscoped request would act beyond them.
    """
    if not can_manage(session, project):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not allowed to act on this project",
        )


def refresh_managed_projects(session: Session) -> None:
    """Re-read the managed projects over the session's TestBench link.

    Memberships change in TestBench while a console session lives on; the
    project refresh is the operator's way to pick that up without signing in
    again. A failed read keeps the previous set, like ``record_projects`` does
    for the project list: a timeout is no reason to lock a project admin out.
    """
    if session.tb_link is None:
        logger.warning("No TestBench link; keeping the managed projects as they are")
        return
    try:
        memberships = session.tb_link.call(get_own_project_memberships)
    except Exception as e:  # keep the last good set rather than failing the refresh
        logger.warning("Could not re-read the TestBench project memberships: %r", e)
        return
    session.managed_projects = managed_projects_from(session.roles, memberships)


def _safe_prompt_file(value: Any) -> bool:
    """Whether *value* is a relative path without ``..`` on any platform.

    ``resolve_prompt_file_path`` accepts absolute and ``..`` paths, which would
    let a project admin probe files outside the prompt directory. Both POSIX and
    Windows spellings are checked, whatever OS the service runs on.
    """
    if not isinstance(value, str) or not value:
        return False
    if value[0] in "/\\" or PureWindowsPath(value).anchor or PurePosixPath(value).is_absolute():
        return False
    return ".." not in re.split(r"[/\\]", value)


def _violates(rel: list[str], value: Any) -> bool:
    """Whether writing *value* at *rel* (the path below a project) is forbidden.

    A dict value stands for every path beneath it, so it is walked with the
    same rules as the equivalent leaf paths. Keys are checked before the walk,
    so an empty dict cannot smuggle a forbidden key in.
    """
    if "llm_config" in rel:
        rest = rel[rel.index("llm_config") + 1 :]
        if rest and rest[0] not in ALLOWED_LLM_FIELDS:
            return True
        if rest == ["provider"] and value == "custom":
            return True
    if len(rel) == _PROMPT_FILE_DEPTH and rel[0] == "agents" and rel[2:] == ["prompt", "file"]:
        return value is not None and not _safe_prompt_file(value)
    if isinstance(value, dict):
        return any(_violates([*rel, key], item) for key, item in value.items())
    return False


def check_config_edits(session: Session, edits: dict[str, Any]) -> None:
    """Refuse (403) edits a non-admin may not make; the admin is never checked.

    A project admin may only touch ``projects."<name>"`` for a project they
    manage, and there only the allowed ``llm_config`` fields and safe
    ``prompt.file`` values. The whole batch is checked before anything is
    planned, so one forbidden path refuses all of it. Paths must already be
    well formed (``validate_edit_paths``).
    """
    if session.is_admin:
        return
    for path, value in edits.items():
        segments = split_path(path)
        allowed = (
            segments[0] == "projects" and len(segments) > 1 and can_manage(session, segments[1])
        )
        if allowed:
            allowed = not _violates(segments[2:], value)
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Not allowed to change {path!r}",
            )


def owns_prompt(session: Session, directory: str, usages: list[PromptUsage]) -> bool:
    """Whether *session* may edit the prompt in *directory* used by *usages*.

    A project admin owns a prompt only when it is a fork (marker in the
    directory name) that is used, and used exclusively by projects they manage.
    "Only Alpha uses it today" is not enough without the marker: the template
    would then change for whoever is pointed at it next. A global usage or an
    unused fork is refused too.
    """
    if session.is_admin:
        return True
    return (
        FORK_MARKER in directory
        and bool(usages)
        and all(u.project is not None and can_manage(session, u.project) for u in usages)
    )


def require_owned_prompt(
    session: Session, prompt_path: Path, prompts_dir: Path, on_disk: dict[str, Any]
) -> None:
    """Refuse (403) a save to a prompt *session* does not own."""
    usages = prompt_usages(prompt_path, prompts_dir, on_disk)
    if not owns_prompt(session, prompt_path.parent.name, usages):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not allowed to change this prompt",
        )


def require_within(plan: WritePlan, fork_dir: Path) -> None:
    """Refuse (403) a save plan that touches any file outside *fork_dir*.

    A fork's document may reference a shared template; writing or deleting it
    would change every prompt that uses it. Paths are resolved first so a
    ``..`` segment or a symlink cannot hide the escape.
    """
    root = fork_dir.resolve()
    touched = [*plan.writes, *plan.creates, *plan.deletes]
    if any(not path.resolve().is_relative_to(root) for path in touched):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not allowed to change files outside this prompt",
        )


def require_fork_target(session: Session, project: str, directory: str | None) -> None:
    """Refuse (403) a fork a non-admin may not make.

    The project must be one they manage, and an explicit directory must carry the
    fork marker so the copy can never land on (or be mistaken for) a shared
    template. The derived default ``<agent>__<slug>`` always carries it.
    """
    require_project_access(session, project)
    if not session.is_admin and directory is not None and FORK_MARKER not in directory:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"A fork directory must contain {FORK_MARKER!r}",
        )
