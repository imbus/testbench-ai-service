from types import SimpleNamespace

import pytest
from fastapi import status

from testbench_ai_service.auth import validate_session_token
from testbench_ai_service.config import AppConfig, ProjectConfig, ProjectUseCaseConfig
from tests.integration.conftest import CYCLE_KEY, PROJECT_KEY, PROJECT_NAME, TOV_KEY, USER_KEY
from tests.integration.helpers import (
    build_locked_structure_tree,
    build_tcs_catalog,
    build_unlocked_structure_tree,
)

_ENDPOINT = "/defect-explanations"

# Patch targets — these are the real functions that touch external systems.
_PATCH_GET_USER_KEY = "testbench_ai_service.utils.usecase.get_user_key"
_PATCH_GET_PROJECT_NAME = "testbench_ai_service.utils.usecase.get_project_name"
_PATCH_HAS_ROLE = "testbench_ai_service.usecases.routes.has_any_required_role"
_PATCH_GET_CATALOG = (
    "testbench_ai_service.usecases.defect_explanations.service.get_test_case_set_catalog"
)
_PATCH_GET_TREE = "testbench_ai_service.utils.usecase.get_test_structure_tree"
_PATCH_GET_ERROR_MSG = "testbench_ai_service.usecases.defect_explanations.service.get_error_message"
_PATCH_CLEAN_UP = "testbench_ai_service.usecases.defect_explanations.service.clean_up_comment"
_PATCH_ADD_EXPLANATIONS = (
    "testbench_ai_service.usecases.defect_explanations.service.add_explanations_to_comment"
)
_PATCH_UPDATE_DESC = "testbench_ai_service.usecases.defect_explanations.service.update_description"


@pytest.fixture(autouse=True)
def patches(mocker):
    """Default happy-path patch state. Tests override only what differs."""
    return SimpleNamespace(
        get_user_key=mocker.patch(_PATCH_GET_USER_KEY, return_value=USER_KEY),
        get_project_name=mocker.patch(_PATCH_GET_PROJECT_NAME, return_value=PROJECT_NAME),
        has_role=mocker.patch(_PATCH_HAS_ROLE, return_value=True),
        get_catalog=mocker.patch(_PATCH_GET_CATALOG, return_value=build_tcs_catalog()),
        get_tree=mocker.patch(_PATCH_GET_TREE, return_value=build_unlocked_structure_tree("exec")),
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

        response = post(_ENDPOINT, cycle_key=CYCLE_KEY)

        assert response.status_code == status.HTTP_202_ACCEPTED
        # get_error_message is called once per test case set in the run phase
        assert patches.get_error_msg.call_count == 2  # noqa: PLR2004


class TestWithWarnings:
    """202 + warnings when some items are locked."""

    def test_partial_lock_returns_202_with_warnings(self, post, patches):
        patches.get_catalog.return_value = {
            **build_tcs_catalog("iTB-TC-66", "17"),
            **build_tcs_catalog("iTB-TC-67", "18"),
        }
        patches.get_tree.side_effect = [
            build_locked_structure_tree("exec"),
            build_unlocked_structure_tree("exec"),
        ]

        body = post(_ENDPOINT, cycle_key=CYCLE_KEY).json()

        assert body.get("warnings") is not None
        assert len(body["warnings"]) == 1


class TestErrorPaths:
    """4xx responses for invalid conditions."""

    def test_missing_cycle_key_returns_409(self, post):
        """Defect explanations require cycle_key — precheck rejects without it."""
        assert post(_ENDPOINT).status_code == status.HTTP_409_CONFLICT

    def test_all_items_locked_returns_409(self, post, patches):
        patches.get_tree.return_value = build_locked_structure_tree("exec")

        assert post(_ENDPOINT, cycle_key=CYCLE_KEY).status_code == status.HTTP_409_CONFLICT

    def test_insufficient_role_returns_403(self, post, patches):
        patches.has_role.return_value = False

        assert post(_ENDPOINT, cycle_key=CYCLE_KEY).status_code == status.HTTP_403_FORBIDDEN

    def test_disabled_usecase_returns_404(self, app, post):
        app.state.config = AppConfig(
            tb_server_url="https://localhost:9443/api/",
            projects={
                PROJECT_NAME: ProjectConfig(
                    usecases={"defect_explanations": ProjectUseCaseConfig(enabled=False)}
                )
            },
        )

        assert post(_ENDPOINT, cycle_key=CYCLE_KEY).status_code == status.HTTP_404_NOT_FOUND

    def test_missing_auth_returns_401(self, app, client):
        app.dependency_overrides.pop(validate_session_token, None)
        response = client.post(
            _ENDPOINT,
            json={"project_key": PROJECT_KEY, "tov_key": TOV_KEY, "cycle_key": CYCLE_KEY},
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_invalid_payload_returns_422(self, client):
        response = client.post(_ENDPOINT, json={"cycle_key": CYCLE_KEY})

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
