def csrf(client) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies["tbai_admin_csrf"]}


class TestGates:
    def test_anonymous_is_refused(self, client):
        assert client.get("/admin/api/models").status_code == 401

    def test_a_non_admin_is_refused(self, client, login):
        login(roles=[])
        response = client.get("/admin/api/models", headers=csrf(client))
        assert response.status_code == 403

    def test_a_browser_shaped_get_without_csrf_succeeds(self, client, login):
        """No CSRF header, because the console's own client never sends one.

        ``apiFetch`` (frontend/src/api/client.ts) attaches ``X-CSRF-Token`` to
        unsafe methods only, so a real browser GET arrives exactly like this
        one. Gating this route on CSRF made every real request a 403 and the
        model picker permanently empty; it also defended nothing, since a read
        of presence booleans by an already-authenticated admin changes no
        state. ``require_admin`` is the access control, and the two tests
        above are what assert it.
        """
        login(roles=["Administrator"])
        assert client.get("/admin/api/models").status_code == 200

    def test_an_admin_is_allowed(self, client, login):
        login(roles=["Administrator"])
        response = client.get("/admin/api/models", headers=csrf(client))
        assert response.status_code == 200


class TestPayload:
    def test_groups_models_by_provider(self, client, login):
        login(roles=["Administrator"])
        body = client.get("/admin/api/models", headers=csrf(client)).json()
        providers = {entry["provider"] for entry in body["providers"]}
        assert {"openai", "anthropic", "azure_openai", "custom"} == providers

    def test_reports_the_routing_family_per_model(self, client, login):
        login(roles=["Administrator"])
        body = client.get("/admin/api/models", headers=csrf(client)).json()
        openai = next(e for e in body["providers"] if e["provider"] == "openai")
        gpt4o = next(m for m in openai["models"] if m["id"] == "gpt-4o")
        assert gpt4o["routing"] == "chat"
        assert gpt4o["source"] == "builtin"

    def test_never_returns_a_key_value(self, client, login, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-secret-value")
        login(roles=["Administrator"])
        response = client.get("/admin/api/models", headers=csrf(client))
        assert "sk-secret-value" not in response.text

    def test_a_project_query_is_accepted(self, client, login):
        login(roles=["Administrator"])
        response = client.get(
            "/admin/api/models", params={"project": "Car Configurator"}, headers=csrf(client)
        )
        assert response.status_code == 200
