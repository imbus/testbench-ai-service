import textwrap

import pytest

VALID = textwrap.dedent(
    """
    name: "Erklärer"
    default_model: "gpt-5.5"
    default_variant: "A"
    variants:
      - name: "A"
        messages:
          - role: "system"
            file: "system.jinja"
    """
).strip()


def csrf(client) -> dict[str, str]:
    """The CSRF header, read off the cookie ``login`` just set on *client*.

    ``login`` (see conftest.py) returns the raw ``/session`` response, not a
    token -- the cookie is what every mutating route actually checks, so
    reading it back is what ``test_config_routes.py`` does too.
    """
    return {"X-CSRF-Token": client.cookies["tbai_admin_csrf"]}


@pytest.fixture
def prompts_dir(tmp_path):
    agent = tmp_path / "de" / "explainer"
    agent.mkdir(parents=True)
    (agent / "prompt.yaml").write_text(VALID, encoding="utf-8")
    (agent / "system.jinja").write_text("Du bist {{ agent.role }}", encoding="utf-8")
    return tmp_path


@pytest.fixture
def app(make_app, prompts_dir):
    return make_app(prompts_dir=str(prompts_dir))


class TestTree:
    def test_lists_the_tree_for_a_signed_in_user(self, client, login):
        login(roles=[])
        body = client.get("/admin/api/prompts").json()
        assert body["languages"][0]["prompts"][0]["agent"] == "explainer"

    def test_refuses_an_anonymous_caller(self, client):
        assert client.get("/admin/api/prompts").status_code == 401


class TestDocument:
    def test_returns_the_document_with_template_bodies(self, client, login):
        login(roles=[])
        body = client.get("/admin/api/prompts/de/explainer").json()
        assert body["variants"][0]["messages"][0]["content"] == "Du bist {{ agent.role }}"

    def test_includes_the_context_skeleton(self, client, login):
        login(roles=[])
        body = client.get("/admin/api/prompts/de/explainer").json()
        assert body["agent_context_skeleton"] == {"role": ""}

    def test_an_unknown_agent_is_404(self, client, login):
        login(roles=[])
        assert client.get("/admin/api/prompts/de/absent").status_code == 404


class TestLint:
    def test_reports_a_syntax_error(self, client, login):
        login(roles=[])
        body = client.post(
            "/admin/api/prompts/lint",
            json={"content": "{% if %}"},
            headers=csrf(client),
        ).json()
        assert body["ok"] is False
        assert body["errors"][0]["line"] == 1

    def test_is_open_to_a_non_admin(self, client, login):
        login(roles=[])
        response = client.post(
            "/admin/api/prompts/lint",
            json={"content": "ok"},
            headers=csrf(client),
        )
        assert response.status_code == 200


class TestRender:
    def test_renders_for_an_admin(self, client, login):
        login(roles=["Administrator"])
        body = client.post(
            "/admin/api/prompts/render",
            json={
                "messages": [
                    {"role": "user", "source": "inline", "file": None, "content": "{{ agent.x }}"}
                ],
                "vars": {},
                "agent_context": {"x": "hallo"},
            },
            headers=csrf(client),
        ).json()
        assert body["messages"][0]["content"] == "hallo"

    def test_refuses_a_non_admin(self, client, login):
        login(roles=[])
        response = client.post(
            "/admin/api/prompts/render",
            json={"messages": [], "vars": {}, "agent_context": {}},
            headers=csrf(client),
        )
        assert response.status_code == 403

    def test_the_sandbox_holds_over_http(self, client, login):
        """The RCE guard, asserted end to end and not only in the unit test."""
        login(roles=["Administrator"])
        body = client.post(
            "/admin/api/prompts/render",
            json={
                "messages": [
                    {
                        "role": "user",
                        "source": "inline",
                        "file": None,
                        "content": "{{ ''.__class__.__mro__ }}",
                    }
                ],
                "vars": {},
                "agent_context": {},
            },
            headers=csrf(client),
        ).json()
        assert body["messages"][0]["error"] is not None


class TestSave:
    def save_body(self, variant_name="A"):
        return {
            "name": "Erklärer",
            "default_model": "gpt-5.5",
            "default_variant": variant_name,
            "variants": [
                {
                    "name": variant_name,
                    "messages": [
                        {
                            "role": "system",
                            "source": "file",
                            "file": "system.jinja",
                            "content": "Neuer Text",
                        }
                    ],
                }
            ],
        }

    def test_writes_the_yaml_and_the_template(self, client, login, prompts_dir):
        login(roles=["Administrator"])
        response = client.put(
            "/admin/api/prompts/de/explainer",
            json=self.save_body(),
            headers=csrf(client),
        )
        assert response.status_code == 200
        assert (prompts_dir / "de/explainer/system.jinja").read_text(
            encoding="utf-8"
        ) == "Neuer Text"

    def test_refuses_a_non_admin(self, client, login):
        login(roles=[])
        response = client.put(
            "/admin/api/prompts/de/explainer",
            json=self.save_body(),
            headers=csrf(client),
        )
        assert response.status_code == 403

    def test_refuses_a_missing_csrf_header(self, client, login):
        login(roles=["Administrator"])
        response = client.put("/admin/api/prompts/de/explainer", json=self.save_body())
        assert response.status_code == 403

    def test_an_invalid_document_writes_nothing(self, client, login, prompts_dir):
        login(roles=["Administrator"])
        before = (prompts_dir / "de/explainer/prompt.yaml").read_text(encoding="utf-8")
        response = client.put(
            "/admin/api/prompts/de/explainer",
            json=self.save_body(variant_name="A") | {"default_variant": "Absent"},
            headers=csrf(client),
        )
        assert response.status_code == 422
        assert (prompts_dir / "de/explainer/prompt.yaml").read_text(encoding="utf-8") == before

    def test_a_rename_orphaning_a_reference_is_refused(self, client, login, app, prompts_dir):
        """`_refuse_orphaned_variants` end to end (design D-note in routes.py).

        The global agents table points ``explainer`` at variant "A". Renaming
        the document's only variant to "B" would leave that reference resolving
        nothing -- ``get_prompt_variant`` would then silently fall back to
        ``default_variant`` instead of erroring, so the save must be refused.
        """
        config_file = prompts_dir / "config.toml"
        config_file.write_text(
            textwrap.dedent(
                """
                [testbench-ai-service.agents.explainer]
                enabled = true
                endpoint_path = "/explain"
                class_path = "testbench_ai_service.agents.defect_explainer.agent.DefectExplainer"

                [testbench-ai-service.agents.explainer.prompt]
                file = "explainer/prompt.yaml"
                variant = "A"
                """
            ).strip(),
            encoding="utf-8",
        )
        app.state.config_path = config_file

        login(roles=["Administrator"])
        response = client.put(
            "/admin/api/prompts/de/explainer",
            json=self.save_body(variant_name="B"),
            headers=csrf(client),
        )
        assert response.status_code == 409
        assert "the global agents table" in response.json()["detail"]
        assert "'A'" in response.json()["detail"]
