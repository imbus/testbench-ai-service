from unittest.mock import MagicMock

import pytest
import requests
from fastapi import status

from testbench_ai_service.auth import validate_auth_token
from testbench_ai_service.dependencies import get_tb_connection


def _make_tb_http_error(status_code: int, message: str) -> requests.exceptions.HTTPError:
    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.json.return_value = {"message": message}
    return requests.exceptions.HTTPError("error", response=mock_response)


def _override_project_lookup_error(app, status_code: int, message: str) -> None:
    mock_conn = MagicMock()
    mock_conn.get_project.side_effect = _make_tb_http_error(status_code, message)
    app.dependency_overrides[get_tb_connection] = lambda: mock_conn


class TestRootRoute:
    def test_root_redirects_to_docs(self, client):
        response = client.get("/", follow_redirects=False)

        assert response.status_code in (307, 308)
        assert "/docs" in response.headers["location"]


class TestGetAgents:
    def test_returns_all_three_use_cases(self, client):
        response = client.get("/agents")

        assert response.status_code == status.HTTP_200_OK
        keys = {uc["key"] for uc in response.json()}
        assert "test_case_set_reviewer" in keys
        assert "test_case_set_describer" in keys
        assert "defect_explainer" in keys

    def test_filter_by_enabled_returns_only_enabled(self, client):
        response = client.get("/agents?enabled=true")

        assert response.status_code == status.HTTP_200_OK
        agents = response.json()
        assert len(agents) > 0
        assert all(agent["enabled"] for agent in agents)

    def test_filter_by_enabled_false_returns_only_disabled(self, client):
        response = client.get("/agents?enabled=false")

        assert response.status_code == status.HTTP_200_OK
        assert all(not uc["enabled"] for uc in response.json())

    @pytest.mark.parametrize(
        ("language", "expected_name"),
        [
            ("en", "Test Case Set Reviewer"),
            ("de", "Testfallsatz-Reviewer"),
        ],
    )
    def test_supports_language_query_param(self, client, language, expected_name):
        response = client.get(f"/agents?keys=test_case_set_reviewer&language={language}")

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert len(body) == 1
        assert body[0]["name"] == expected_name

    def test_requires_auth_token(self, app, client):
        app.dependency_overrides.pop(validate_auth_token, None)
        response = client.get("/agents")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestGetAgentDetails:
    def test_returns_agent_details_for_valid_agent(self, client):
        response = client.get("/agents/test_case_set_reviewer")

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert body["key"] == "test_case_set_reviewer"
        assert "name" in body
        assert "enabled" in body

    @pytest.mark.parametrize(
        ("language", "expected_name"),
        [
            ("en", "Test Case Set Reviewer"),
            ("de", "Testfallsatz-Reviewer"),
        ],
    )
    def test_supports_language_query_param(self, client, language, expected_name):
        response = client.get(f"/agents/test_case_set_reviewer?language={language}")

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["name"] == expected_name

    def test_unknown_agent_returns_404(self, client):
        response = client.get("/agents/does_not_exist")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_requires_auth_token(self, app, client):
        app.dependency_overrides.pop(validate_auth_token, None)
        response = client.get("/agents/test_case_set_reviewer")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestGetPromptDetails:
    def test_returns_prompt_details_for_valid_agent(self, client):
        response = client.get("/agents/test_case_set_reviewer/prompt")

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert "variants" in body
        assert len(body["variants"]) > 0
        assert "name" in body
        assert "default_variant" in body

    def test_returns_variants_with_vars(self, client):
        response = client.get("/agents/test_case_set_reviewer/prompt")

        assert response.status_code == status.HTTP_200_OK
        for variant in response.json()["variants"]:
            assert "name" in variant
            assert "vars" in variant

    @pytest.mark.parametrize(
        ("language", "expected_name", "expected_default_variant"),
        [
            ("en", "Test Case Set Reviewer", "Full Review"),
            ("de", "Testfallsatz-Reviewer", "Umfassende Prüfung"),
        ],
    )
    def test_supports_language_query_param(
        self, client, language, expected_name, expected_default_variant
    ):
        response = client.get(f"/agents/test_case_set_reviewer/prompt?language={language}")

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert body["name"] == expected_name
        assert body["default_variant"] == expected_default_variant

    def test_unknown_agent_returns_404(self, client):
        response = client.get("/agents/does_not_exist/prompt")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_requires_auth_token(self, app, client):
        app.dependency_overrides.pop(validate_auth_token, None)
        response = client.get("/agents/test_case_set_reviewer/prompt")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestProjectKeyResolution:
    @pytest.mark.parametrize(
        "endpoint",
        [
            "/agents",
            "/agents/test_case_set_reviewer",
            "/agents/test_case_set_reviewer/prompt",
        ],
    )
    def test_invalid_project_key_returns_404(self, app, client, endpoint):
        _override_project_lookup_error(app, status.HTTP_404_NOT_FOUND, "Project not found")

        response = client.get(f"{endpoint}?project_key=does-not-exist")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.json()["detail"] == "Project not found"
