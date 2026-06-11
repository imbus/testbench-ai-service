from types import SimpleNamespace
from unittest.mock import patch as mock_patch

import pytest
from fastapi import status

from testbench_ai_service.auth import validate_auth_token
from testbench_ai_service.config import AppConfig
from testbench_ai_service.models.config import ProjectAgentConfig, ProjectConfig
from testbench_ai_service.models.testbench import ProjectRole
from tests.integration.conftest import CYCLE_KEY, PROJECT_KEY, PROJECT_NAME, TOV_KEY
from tests.integration.helpers import (
    build_locked_structure_tree,
    build_multi_unlocked_structure_tree,
    build_tcs_catalog,
    build_two_node_structure_tree,
    build_unlocked_structure_tree,
)

_ENDPOINT = "/defect-explanations"

_PATCH_GET_PROJECT_NAME = "testbench_ai_service.utils.agent.get_project_name"
_PATCH_GET_CATALOG = "testbench_ai_service.agents.defect_explainer.agent.get_test_case_set_catalog"
_PATCH_GET_TREE = "testbench_ai_service.utils.testbench.get_test_structure_tree"
_PATCH_GET_PROJECT_ROLES = "testbench_ai_service.agents.routes.get_project_roles"
_PATCH_GET_ERROR_MSG = "testbench_ai_service.agents.defect_explainer.agent.get_error_message"
_PATCH_CLEAN_UP = "testbench_ai_service.agents.defect_explainer.agent.clean_up_comment"
_PATCH_ADD_EXPLANATIONS = (
    "testbench_ai_service.agents.defect_explainer.agent.add_explanations_to_comment"
)
_PATCH_UPDATE_DESC = "testbench_ai_service.agents.defect_explainer.agent.update_description"


@pytest.fixture(autouse=True)
def patches(mocker):
    """Default happy-path patch state. Tests override only what differs."""
    return SimpleNamespace(
        get_project_name=mocker.patch(_PATCH_GET_PROJECT_NAME, return_value=PROJECT_NAME),
        get_catalog=mocker.patch(_PATCH_GET_CATALOG, return_value=build_tcs_catalog()),
        get_tree=mocker.patch(_PATCH_GET_TREE, return_value=build_unlocked_structure_tree("exec")),
        get_project_roles=mocker.patch(
            _PATCH_GET_PROJECT_ROLES,
            return_value=[ProjectRole.Tester],
        ),
        get_error_msg=mocker.patch(_PATCH_GET_ERROR_MSG, return_value={}),
        clean_up=mocker.patch(_PATCH_CLEAN_UP, return_value="<html><body></body></html>"),
        add_explanations=mocker.patch(
            _PATCH_ADD_EXPLANATIONS, return_value="<html><body></body></html>"
        ),
        update_desc=mocker.patch(_PATCH_UPDATE_DESC, return_value=None),
    )


class TestHappyPath:
    """202 responses for well-formed requests."""

    def test_returns_202_with_cycle_key(self, post):
        assert post(_ENDPOINT, cycle_key=CYCLE_KEY).status_code == status.HTTP_202_ACCEPTED

    def test_response_body_is_accepted(self, post):
        assert post(_ENDPOINT, cycle_key=CYCLE_KEY).json()["status"] == "accepted"

    def test_multiple_items_all_processed(self, post, patches):
        """Two test-case sets in the catalog → both are processed."""
        patches.get_catalog.return_value = {
            **build_tcs_catalog("iTB-TC-66", "17"),
            **build_tcs_catalog("iTB-TC-67", "18"),
        }
        patches.get_tree.return_value = build_multi_unlocked_structure_tree("exec")

        response = post(_ENDPOINT, cycle_key=CYCLE_KEY, element_type="TESTTHEME")

        assert response.status_code == status.HTTP_202_ACCEPTED
        # get_error_message is called once per test case set in the run phase
        assert patches.get_error_msg.call_count == 2


class TestWithWarnings:
    """202 + warnings when some items are locked."""

    def test_partial_lock_returns_202_with_warnings(self, post, patches):
        patches.get_catalog.return_value = {
            **build_tcs_catalog("iTB-TC-66", "17"),
            **build_tcs_catalog("iTB-TC-67", "18"),
        }
        patches.get_tree.return_value = build_two_node_structure_tree("exec")

        body = post(_ENDPOINT, cycle_key=CYCLE_KEY, element_type="TESTTHEME").json()

        assert body.get("warnings") is not None
        assert len(body["warnings"]) == 1


class TestErrorPaths:
    """4xx responses for invalid conditions."""

    def test_missing_execution_data_returns_409(self, post, patches):
        """Precheck rejects when execution data is absent for all items."""
        patches.get_tree.return_value = build_unlocked_structure_tree("spec")

        assert post(_ENDPOINT, cycle_key=CYCLE_KEY).status_code == status.HTTP_409_CONFLICT

    def test_all_items_locked_returns_409(self, post, patches):
        patches.get_tree.return_value = build_locked_structure_tree("exec")

        assert post(_ENDPOINT, cycle_key=CYCLE_KEY).status_code == status.HTTP_409_CONFLICT

    def test_insufficient_role_returns_403(self, post, patches):
        patches.get_project_roles.return_value = []

        assert post(_ENDPOINT, cycle_key=CYCLE_KEY).status_code == status.HTTP_403_FORBIDDEN

    def test_disabled_agent_returns_404(self, app, post):
        with mock_patch("testbench_ai_service.config.validate_tb_server_url"):
            app.state.config = AppConfig(
                tb_server_url="https://localhost:9443/api/",
                projects={
                    PROJECT_NAME: ProjectConfig(
                        agents={"defect_explainer": ProjectAgentConfig(enabled=False)}
                    )
                },
            )

        assert post(_ENDPOINT, cycle_key=CYCLE_KEY).status_code == status.HTTP_404_NOT_FOUND

    def test_missing_auth_returns_401(self, app, client):
        app.dependency_overrides.pop(validate_auth_token, None)
        response = client.post(
            _ENDPOINT,
            json={"project_key": PROJECT_KEY, "tov_key": TOV_KEY, "cycle_key": CYCLE_KEY},
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_invalid_payload_returns_422(self, client):
        response = client.post(_ENDPOINT, json={"cycle_key": CYCLE_KEY})

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
