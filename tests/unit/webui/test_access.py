from unittest.mock import MagicMock

import pytest
import requests
from fastapi import HTTPException

from testbench_ai_service.models.testbench import ProjectMember
from testbench_ai_service.webui.access import (
    can_manage,
    check_config_edits,
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


_OWN = frozenset({"Alpha", "Release 2.0"})


@pytest.mark.parametrize(
    "edits",
    [
        {"language": "en"},
        {'projects."Beta".language': "en"},
        # One allowed path must not carry a forbidden one along.
        {'projects."Alpha".language': "en", 'projects."Beta".language': "en"},
        {'projects."Alpha".llm_config.class_path': "x.Y"},
        {'projects."Alpha".llm_config.azure_endpoint': "https://evil"},
        {'projects."Alpha".llm_config.auth_method': "azure_ad"},
        {'projects."Alpha".llm_config.provider': "custom"},
        # A table written as a value is held to the same rules as its leaves.
        {'projects."Alpha".llm_config': {"provider": "custom"}},
        {'projects."Alpha"': {"llm_config": {"class_path": "x.Y"}}},
    ],
)
def test_project_admin_edit_is_refused(edits):
    with pytest.raises(HTTPException) as exc:
        check_config_edits(_session(False, _OWN), edits)
    assert exc.value.status_code == 403


@pytest.mark.parametrize(
    "edits",
    [
        {'projects."Alpha".language': "en"},
        {'projects."Release 2.0".agents.test_case_set_reviewer.enabled': False},
        {'projects."Alpha".llm_config.model': "gpt-4o"},
        {'projects."Alpha".llm_config.provider': "anthropic"},
        {'projects."Alpha"': None},
    ],
)
def test_project_admin_edit_is_allowed(edits):
    check_config_edits(_session(False, _OWN), edits)


def test_admin_is_never_checked():
    edits = {"language": "en", 'projects."Beta".llm_config.class_path': "x"}
    check_config_edits(_session(True), edits)


def test_refusal_names_the_first_offending_path():
    with pytest.raises(HTTPException) as exc:
        check_config_edits(
            _session(False, _OWN),
            {'projects."Alpha".language': "en", 'projects."Beta".language': "en"},
        )
    assert "Beta" in exc.value.detail
