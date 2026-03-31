from fastapi import status

from testbench_ai_service.auth import validate_session_token


class TestRootRoute:
    def test_root_redirects_to_docs(self, client):
        response = client.get("/", follow_redirects=False)

        assert response.status_code in (307, 308)
        assert "/docs" in response.headers["location"]


class TestGetUsecases:
    def test_returns_all_three_use_cases(self, client):
        response = client.get("/usecases")

        assert response.status_code == status.HTTP_200_OK
        keys = {uc["key"] for uc in response.json()}
        assert "test_case_set_reviews" in keys
        assert "test_case_set_descriptions" in keys
        assert "defect_explanations" in keys

    def test_filter_by_enabled_returns_only_enabled(self, client):
        response = client.get("/usecases?enabled=true")

        assert response.status_code == status.HTTP_200_OK
        usecases = response.json()
        assert len(usecases) > 0
        assert all(uc["enabled"] for uc in usecases)

    def test_filter_by_enabled_false_returns_only_disabled(self, client):
        response = client.get("/usecases?enabled=false")

        assert response.status_code == status.HTTP_200_OK
        assert all(not uc["enabled"] for uc in response.json())

    def test_requires_auth_token(self, app, client):
        app.dependency_overrides.pop(validate_session_token, None)
        response = client.get("/usecases")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestGetPromptDetails:
    def test_returns_prompt_details_for_valid_usecase(self, client):
        response = client.get("/usecases/test_case_set_reviews/prompt")

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert "variants" in body
        assert len(body["variants"]) > 0
        assert "name" in body
        assert "default_variant" in body

    def test_returns_variants_with_placeholders(self, client):
        response = client.get("/usecases/test_case_set_reviews/prompt")

        assert response.status_code == status.HTTP_200_OK
        for variant in response.json()["variants"]:
            assert "name" in variant
            assert "placeholders" in variant

    def test_unknown_usecase_returns_404(self, client):
        response = client.get("/usecases/does_not_exist/prompt")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_requires_auth_token(self, app, client):
        app.dependency_overrides.pop(validate_session_token, None)
        response = client.get("/usecases/test_case_set_reviews/prompt")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
