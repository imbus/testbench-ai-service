from fastapi import status

from testbench_ai_service.auth import get_auth_info


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

    def test_requires_auth_token(self, app, client):
        app.dependency_overrides.pop(get_auth_info, None)
        response = client.get("/agents")

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

    def test_unknown_agent_returns_404(self, client):
        response = client.get("/agents/does_not_exist/prompt")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_requires_auth_token(self, app, client):
        app.dependency_overrides.pop(get_auth_info, None)
        response = client.get("/agents/test_case_set_reviewer/prompt")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
