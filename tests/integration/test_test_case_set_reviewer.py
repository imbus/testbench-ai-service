from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import status

from testbench_ai_service.auth import get_auth_info
from testbench_ai_service.config import AppConfig, ProjectAgentConfig, ProjectConfig
from tests.integration.conftest import CYCLE_KEY, PROJECT_KEY, PROJECT_NAME, TOV_KEY
from tests.integration.helpers import (
    build_locked_structure_tree,
    build_tcs_catalog,
    build_unlocked_structure_tree,
)

_ENDPOINT = "/test-case-set-reviews"

# Patch targets — these are the real functions that touch external systems.
_PATCH_GET_PROJECT_NAME = "testbench_ai_service.utils.agent.get_project_name"
_PATCH_HAS_ROLE = "testbench_ai_service.agents.routes.has_any_required_role"
_PATCH_GET_CATALOG = (
    "testbench_ai_service.agents.test_case_set_reviewer.agent.get_test_case_set_catalog"
)
_PATCH_GET_TREE = "testbench_ai_service.utils.agent.get_test_structure_tree"
_PATCH_GET_REVIEW_COMMENT = (
    "testbench_ai_service.agents.test_case_set_reviewer.agent.get_review_comment_for_test_case_set"
)
_PATCH_PATCH_STARTED = "testbench_ai_service.agents.test_case_set_reviewer.agent.patch_review_started_for_test_structure_element"
_PATCH_PATCH_RESULT = "testbench_ai_service.agents.test_case_set_reviewer.agent.patch_review_result_for_test_structure_element"


@pytest.fixture(autouse=True)
def patches(mocker):
    """Default happy-path patch state. Tests override only what differs."""
    return SimpleNamespace(
        get_project_name=mocker.patch(_PATCH_GET_PROJECT_NAME, return_value=PROJECT_NAME),
        has_role=mocker.patch(_PATCH_HAS_ROLE, return_value=True),
        get_catalog=mocker.patch(_PATCH_GET_CATALOG, return_value=build_tcs_catalog()),
        get_tree=mocker.patch(_PATCH_GET_TREE, return_value=build_unlocked_structure_tree("spec")),
        get_review_comment=mocker.patch(
            _PATCH_GET_REVIEW_COMMENT, new_callable=AsyncMock, return_value=""
        ),
        patch_started=mocker.patch(_PATCH_PATCH_STARTED, new_callable=AsyncMock, return_value=None),
        patch_result=mocker.patch(_PATCH_PATCH_RESULT, new_callable=AsyncMock, return_value=None),
    )


class TestHappyPath:
    """202 responses for well-formed requests."""

    def test_returns_202_with_cycle_key(self, post):
        assert post(_ENDPOINT, cycle_key=CYCLE_KEY).status_code == status.HTTP_202_ACCEPTED

    def test_returns_202_without_cycle_key(self, post):
        """ToV-level review — no cycle_key in the request."""
        assert post(_ENDPOINT).status_code == status.HTTP_202_ACCEPTED

    def test_response_body_is_accepted(self, post):
        assert post(_ENDPOINT, cycle_key=CYCLE_KEY).json()["status"] == "accepted"

    def test_multiple_items_all_reviewed(self, post, patches):
        """Two test case sets in the catalog → both get a review-started + review-result patch."""
        patches.get_catalog.return_value = {
            **build_tcs_catalog("iTB-TC-66", "17"),
            **build_tcs_catalog("iTB-TC-67", "18"),
        }

        response = post(_ENDPOINT, cycle_key=CYCLE_KEY)

        assert response.status_code == status.HTTP_202_ACCEPTED
        assert patches.patch_started.call_count == 2  # noqa: PLR2004
        assert patches.patch_result.call_count == 2  # noqa: PLR2004


class TestWithWarnings:
    """202 + warnings when some items are locked."""

    def test_partial_lock_returns_202_with_warnings(self, post, patches):
        """First item locked, second item free → 202 with one warning."""
        patches.get_catalog.return_value = {
            **build_tcs_catalog("iTB-TC-66", "17"),
            **build_tcs_catalog("iTB-TC-67", "18"),
        }
        patches.get_tree.side_effect = [
            build_locked_structure_tree("spec"),
            build_unlocked_structure_tree("spec"),
        ]

        body = post(_ENDPOINT, cycle_key=CYCLE_KEY).json()

        assert body.get("warnings") is not None
        assert len(body["warnings"]) == 1


class TestErrorPaths:
    """4xx responses for invalid conditions."""

    def test_all_items_locked_returns_409(self, post, patches):
        """Precheck fails when every item is locked — service returns 409 Conflict."""
        patches.get_tree.return_value = build_locked_structure_tree("spec")

        assert post(_ENDPOINT, cycle_key=CYCLE_KEY).status_code == status.HTTP_409_CONFLICT

    def test_insufficient_role_returns_403(self, post, patches):
        patches.has_role.return_value = False

        assert post(_ENDPOINT, cycle_key=CYCLE_KEY).status_code == status.HTTP_403_FORBIDDEN

    def test_disabled_agent_returns_404(self, app, post):
        """Use case disabled for this project → 404 Not Found."""
        app.state.config = AppConfig(
            tb_server_url="https://localhost:9443/api/",
            projects={
                PROJECT_NAME: ProjectConfig(
                    agents={"test_case_set_reviewer": ProjectAgentConfig(enabled=False)}
                )
            },
        )

        assert post(_ENDPOINT, cycle_key=CYCLE_KEY).status_code == status.HTTP_404_NOT_FOUND

    def test_missing_auth_returns_401(self, app, client):
        """No Authorization header → 401 Unauthorized."""
        app.dependency_overrides.pop(get_auth_info, None)
        response = client.post(_ENDPOINT, json={"project_key": PROJECT_KEY, "tov_key": TOV_KEY})

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_invalid_payload_returns_422(self, client):
        """Missing required fields → 422 Unprocessable Entity from Pydantic validation."""
        response = client.post(_ENDPOINT, json={"cycle_key": CYCLE_KEY})

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
