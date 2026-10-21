from unittest.mock import MagicMock

import pytest
import requests
from fastapi import HTTPException

from testbench_ai_service.models.testbench import ProjectMember
from testbench_ai_service.webui.access import (
    can_manage,
    check_config_edits,
    managed_projects_from,
    owns_prompt,
    read_managed_projects,
    require_within,
)
from testbench_ai_service.webui.models import PromptUsage
from testbench_ai_service.webui.prompts import WritePlan
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
        # Only the projects table is theirs, even if a name matches a managed project.
        {'agents."Alpha".class_path': "x.Y"},
        {'llm_config."Alpha".model': "x"},
        # llm_config is an allow-list: unknown extras are refused too.
        {'projects."Alpha".llm_config.deployment_mapping': {"a": "b"}},
        {'projects."Alpha".llm_config._strict_response_validation': True},
        {'projects."Alpha".llm_config.class_path': {}},
        {'projects."Alpha".llm_config': {"model": "x", "deployment_mapping": {"a": "b"}}},
        {'projects."Alpha"': {"llm_config": {"model": "x", "deployment_mapping": {}}}},
        # prompt.file must stay a relative path inside the prompt directory.
        {'projects."Alpha".agents.r.prompt.file': "/etc/x.yaml"},
        {'projects."Alpha".agents.r.prompt.file': r"C:\x\prompt.yaml"},
        {'projects."Alpha".agents.r.prompt.file': r"\\server\share\p.yaml"},
        {'projects."Alpha".agents.r.prompt.file': r"../../x/prompt.yaml"},
        {'projects."Alpha".agents.r.prompt.file': r"de\..\..\x.yaml"},
        {'projects."Alpha".agents.r.prompt.file': 5},
        {'projects."Alpha".agents.r.prompt': {"file": "/etc/x.yaml"}},
        {'projects."Alpha".agents.r': {"prompt": {"file": "../x.yaml"}}},
        {'projects."Alpha"': {"agents": {"r": {"prompt": {"file": "/etc/x.yaml"}}}}},
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
        {
            'projects."Alpha".llm_config': {
                "provider": "azure",
                "model": "m",
                "timeout": 30,
                "max_retries": 2,
                "api_version": "v1",
                "extra_models": {"a": "b"},
            }
        },
        {'projects."Alpha".agents.r.prompt.file': "de/reviewer__alpha/prompt.yaml"},
        {'projects."Alpha".agents.r.prompt.file': None},
        {'projects."Alpha".agents.r.prompt': {"file": "de/p.yaml"}},
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


def _usage(project: str | None, agent: str = "reviewer") -> PromptUsage:
    return PromptUsage(agent=agent, project=project)


def test_owns_prompt_requires_fork_marker():
    # A shared template only one project happens to use today: no fork, no edit.
    session = _session(False, frozenset({"Alpha"}))
    assert owns_prompt(session, "test_case_set_reviewer", [_usage("Alpha")]) is False


def test_owns_prompt_refuses_shared_fork():
    session = _session(False, frozenset({"Alpha"}))
    assert owns_prompt(session, "reviewer__alpha", [_usage("Alpha"), _usage("Beta")]) is False


def test_owns_prompt_refuses_global_usage():
    session = _session(False, frozenset({"Alpha"}))
    assert owns_prompt(session, "reviewer__alpha", [_usage("Alpha"), _usage(None)]) is False


def test_owns_prompt_refuses_unused_fork():
    session = _session(False, frozenset({"Alpha"}))
    assert owns_prompt(session, "reviewer__alpha", []) is False


def test_owns_prompt_accepts_own_fork():
    session = _session(False, frozenset({"Alpha"}))
    assert owns_prompt(session, "reviewer__alpha", [_usage("Alpha")]) is True


def test_owns_prompt_is_always_true_for_an_admin():
    assert owns_prompt(_session(True), "reviewer", []) is True


def test_require_within_refuses_shared_template(tmp_path):
    fork = tmp_path / "de" / "reviewer__alpha"
    shared = tmp_path / "de" / "reviewer" / "system.jinja"
    plan = WritePlan(writes={fork / "prompt.yaml": "x", shared: "y"})
    with pytest.raises(HTTPException) as e:
        require_within(plan, fork)
    assert e.value.status_code == 403


def test_require_within_refuses_a_deletion_outside_the_fork(tmp_path):
    fork = tmp_path / "de" / "reviewer__alpha"
    plan = WritePlan(deletes=[tmp_path / "de" / "reviewer" / "user.jinja"])
    with pytest.raises(HTTPException):
        require_within(plan, fork)


def test_require_within_refuses_dotdot_escapes(tmp_path):
    fork = tmp_path / "de" / "reviewer__alpha"
    plan = WritePlan(writes={fork / ".." / "reviewer" / "system.jinja": "y"})
    with pytest.raises(HTTPException):
        require_within(plan, fork)


def test_require_within_accepts_files_inside_the_fork(tmp_path):
    fork = tmp_path / "de" / "reviewer__alpha"
    plan = WritePlan(
        writes={fork / "prompt.yaml": "x"},
        creates={fork / "new.jinja"},
        deletes=[fork / "old.jinja"],
    )
    require_within(plan, fork)
