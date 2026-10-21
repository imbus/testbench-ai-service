from unittest.mock import MagicMock

import requests

from testbench_ai_service.models.testbench import ProjectMember
from testbench_ai_service.webui.access import (
    can_manage,
    managed_projects_from,
    read_managed_projects,
)
from testbench_ai_service.webui.session import SessionStore


def _member(project: str, roles: list[str]) -> ProjectMember:
    return ProjectMember(
        userKey="u-1",
        userLogin="a.mueller",
        userName="A. Mueller",
        projectKey=f"key-{project}",
        projectName=project,
        roles=roles,
    )


def test_project_admin_manages_only_testmanager_projects():
    members = [_member("Alpha", ["TestManager"]), _member("Beta", ["Tester"])]
    assert managed_projects_from(["ProjectAdministrator"], members) == frozenset({"Alpha"})


def test_testmanager_without_global_project_admin_role_manages_nothing():
    assert (
        managed_projects_from(["ProjectUser"], [_member("Alpha", ["TestManager"])]) == frozenset()
    )


def test_read_managed_projects_never_raises():
    conn = MagicMock()
    conn.session.get.side_effect = requests.exceptions.HTTPError("404")
    assert read_managed_projects(conn, ["ProjectAdministrator"]) == frozenset()


def test_read_managed_projects_skips_the_call_for_other_roles():
    conn = MagicMock()
    read_managed_projects(conn, ["ProjectUser"])
    conn.session.get.assert_not_called()


def _session(is_admin: bool, managed: frozenset[str] = frozenset()):
    return SessionStore().create(
        username="u", roles=[], is_admin=is_admin, managed_projects=managed
    )


def test_can_manage():
    admin = _session(True)
    assert can_manage(admin, "Anything") is True
    assert can_manage(admin, None) is True

    project_admin = _session(False, frozenset({"Alpha"}))
    assert can_manage(project_admin, "Alpha") is True
    assert can_manage(project_admin, "Beta") is False
    assert can_manage(project_admin, None) is False
