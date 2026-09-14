import textwrap
from pathlib import Path

import pytest
from fastapi import HTTPException

from testbench_ai_service.webui.models import ConfigIssue, PreviewResponse

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
          - role: "user"
            file: "user.jinja"
    """
).strip()

#: What a save posting SAVE_BODY_DROPPING_USER_JINJA would do to the on-disk
#: document: drop the "user" message, leaving the template it pointed at
#: unreferenced and therefore deletable (design 5.5).
SAVE_BODY_DROPPING_USER_JINJA = {
    "name": "Erklärer",
    "default_model": "gpt-5.5",
    "default_variant": "A",
    "variants": [
        {
            "name": "A",
            "messages": [
                {
                    "role": "system",
                    "source": "file",
                    "file": "system.jinja",
                    "content": "Du bist {{ agent.role }}",
                }
            ],
        }
    ],
}

#: A document whose default_variant names no variant at all -- refused by
#: `_validate_document` the same way for both the plan route and the save.
SAVE_BODY_WITH_BAD_DEFAULT_VARIANT = {
    "name": "Erklärer",
    "default_model": "gpt-5.5",
    "default_variant": "Absent",
    "variants": [
        {
            "name": "A",
            "messages": [{"role": "system", "source": "inline", "file": None, "content": "hallo"}],
        }
    ],
}


def csrf(client) -> dict[str, str]:
    """The CSRF header, read off the cookie ``login`` just set on *client*.

    ``login`` (see conftest.py) returns the raw ``/session`` response, not a
    token -- the cookie is what every mutating route actually checks, so
    reading it back is what ``test_config_routes.py`` does too.
    """
    return {"X-CSRF-Token": client.cookies["tbai_admin_csrf"]}


@pytest.fixture
def prompt_tree(tmp_path):
    agent = tmp_path / "de" / "explainer"
    agent.mkdir(parents=True)
    (agent / "prompt.yaml").write_text(VALID, encoding="utf-8")
    (agent / "system.jinja").write_text("Du bist {{ agent.role }}", encoding="utf-8")
    (agent / "user.jinja").write_text("Nutzer-Text", encoding="utf-8")
    return tmp_path


@pytest.fixture
def config_path(prompt_tree) -> Path:
    """A config.toml pointing ``prompts_dir`` at *prompt_tree*.

    A fork's proposed config is validated by building a real ``AppConfig``
    (``validate_config_dict``), which resolves every ``prompt.file`` against
    ``prompts_dir`` -- so the fork tests need that field to name the same
    directory the running app was built with, not the module's real prompts
    directory a bare, path-less config.toml would default to.
    """
    path = prompt_tree / "config.toml"
    path.write_text(
        f'[testbench-ai-service]\nprompts_dir = "{prompt_tree.resolve().as_posix()}"\n',
        encoding="utf-8",
    )
    return path


@pytest.fixture
def app(make_app, prompt_tree, config_path):
    application = make_app(prompts_dir=str(prompt_tree))
    application.state.config_path = config_path
    return application


class _AdminClient:
    """A signed-in admin client that attaches the CSRF header automatically.

    Mirrors what the console's own fetch wrapper does (it reads the cookie
    ``login`` sets and adds it to every mutating request) -- see the module's
    ``csrf()`` helper, which every other test class in this file calls by
    hand. The plan/fork tests read like an operator's request rather than an
    HTTP fixture, so this fixture, not another explicit header, is what makes
    that possible.
    """

    def __init__(self, client):
        self._client = client

    def _headers(self) -> dict[str, str]:
        token = self._client.cookies.get("tbai_admin_csrf")
        return {"X-CSRF-Token": token} if token else {}

    def get(self, url, **kwargs):
        return self._client.get(url, **kwargs)

    def post(self, url, **kwargs):
        kwargs.setdefault("headers", self._headers())
        return self._client.post(url, **kwargs)

    def put(self, url, **kwargs):
        kwargs.setdefault("headers", self._headers())
        return self._client.put(url, **kwargs)

    def delete(self, url, **kwargs):
        kwargs.setdefault("headers", self._headers())
        return self._client.delete(url, **kwargs)


@pytest.fixture
def admin_client(client, login):
    login(roles=["Administrator"])
    return _AdminClient(client)


class TestTree:
    def test_lists_the_tree_for_a_signed_in_user(self, client, login):
        login(roles=[])
        body = client.get("/admin/api/prompts").json()
        assert body["languages"][0]["prompts"][0]["agent"] == "explainer"

    def test_refuses_an_anonymous_caller(self, client):
        assert client.get("/admin/api/prompts").status_code == 401

    def test_an_unreadable_config_still_lists_the_tree(self, client, login, config_path):
        """The tree is how an operator would reach a broken prompt to fix it;
        an unreadable config.toml must not cost them that (routes.py's
        try/except around read_config_file in read_prompt_tree).
        """
        config_path.write_text("not toml [", encoding="utf-8")
        login(roles=[])
        response = client.get("/admin/api/prompts")
        assert response.status_code == 200
        body = response.json()
        assert body["languages"][0]["prompts"][0]["agent"] == "explainer"
        assert body["languages"][0]["prompts"][0]["used_by"] == []


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

    def test_writes_the_yaml_and_the_template(self, client, login, prompt_tree):
        login(roles=["Administrator"])
        response = client.put(
            "/admin/api/prompts/de/explainer",
            json=self.save_body(),
            headers=csrf(client),
        )
        assert response.status_code == 200
        assert (prompt_tree / "de/explainer/system.jinja").read_text(
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

    def test_an_invalid_document_writes_nothing(self, client, login, prompt_tree):
        login(roles=["Administrator"])
        before = (prompt_tree / "de/explainer/prompt.yaml").read_text(encoding="utf-8")
        response = client.put(
            "/admin/api/prompts/de/explainer",
            json=self.save_body(variant_name="A") | {"default_variant": "Absent"},
            headers=csrf(client),
        )
        assert response.status_code == 422
        assert (prompt_tree / "de/explainer/prompt.yaml").read_text(encoding="utf-8") == before

    def test_names_a_deleted_template_and_nothing_created(self, client, login, prompt_tree):
        """PromptSaveResponse.created/deleted/deletions_skipped (Task 6's addition
        to the PUT -- Task 4 deliberately left them off `save_prompt`'s response).
        """
        login(roles=["Administrator"])
        response = client.put(
            "/admin/api/prompts/de/explainer",
            # save_body() carries only the system.jinja message, dropping the
            # user.jinja one the on-disk document (VALID) declares -- so this
            # save orphans user.jinja and it must be deleted.
            json=self.save_body(),
            headers=csrf(client),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["deleted"] == [str(prompt_tree / "de/explainer/user.jinja")]
        assert body["created"] == []
        assert not (prompt_tree / "de/explainer/user.jinja").exists()

    def test_reports_why_a_deletion_was_skipped(self, client, login, prompt_tree):
        """An unparseable prompt anywhere blocks every deletion (design 5.5) --
        the save still succeeds, but `deletions_skipped` must say why nothing
        was removed rather than silently keeping user.jinja with no comment.
        """
        broken = prompt_tree / "de" / "broken"
        broken.mkdir()
        (broken / "prompt.yaml").write_text("name: [unclosed", encoding="utf-8")

        login(roles=["Administrator"])
        response = client.put(
            "/admin/api/prompts/de/explainer",
            json=self.save_body(),
            headers=csrf(client),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["deleted"] == []
        assert body["deletions_skipped"] is not None
        assert (prompt_tree / "de/explainer/user.jinja").exists()

    def test_a_rename_orphaning_a_reference_is_refused(self, client, login, app, prompt_tree):
        """`_refuse_orphaned_variants` end to end (design D-note in routes.py).

        The global agents table points ``explainer`` at variant "A". Renaming
        the document's only variant to "B" would leave that reference resolving
        nothing -- ``get_prompt_variant`` would then silently fall back to
        ``default_variant`` instead of erroring, so the save must be refused.
        """
        config_file = prompt_tree / "config.toml"
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


def test_the_plan_route_names_creations_updates_and_deletions(admin_client, prompt_tree):
    response = admin_client.post(
        "/admin/api/prompts/de/explainer/plan",
        json=SAVE_BODY_DROPPING_USER_JINJA,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["deleted"] == [str(prompt_tree / "de/explainer/user.jinja")]
    assert body["deletions_skipped"] is None
    # The document itself changed (one message removed), so it is "updated";
    # system.jinja's content is unchanged, so nothing is "created".
    assert body["updated"] == [str(prompt_tree / "de/explainer/prompt.yaml")]
    assert body["created"] == []


def test_the_plan_route_touches_nothing(admin_client, prompt_tree):
    before = (prompt_tree / "de/explainer/prompt.yaml").read_bytes()
    admin_client.post("/admin/api/prompts/de/explainer/plan", json=SAVE_BODY_DROPPING_USER_JINJA)
    assert (prompt_tree / "de/explainer/prompt.yaml").read_bytes() == before
    assert (prompt_tree / "de/explainer/user.jinja").exists()


def test_the_plan_route_refuses_a_non_admin(client, login):
    login(roles=["Project User"])
    # With the CSRF header attached, only require_admin can still produce the
    # 403 -- without it, the CSRF gate alone would explain the status code and
    # the admin gate could be silently missing.
    response = client.post("/admin/api/prompts/de/explainer/plan", json={}, headers=csrf(client))
    assert response.status_code == 403


def test_the_plan_route_reports_a_refusal_the_way_the_save_would(admin_client):
    response = admin_client.post(
        "/admin/api/prompts/de/explainer/plan", json=SAVE_BODY_WITH_BAD_DEFAULT_VARIANT
    )
    assert response.status_code == 422


def test_the_plan_route_refuses_a_missing_csrf_header(client, login):
    login(roles=["Administrator"])
    response = client.post("/admin/api/prompts/de/explainer/plan", json={})
    assert response.status_code == 403


def test_a_fork_creates_the_files_and_repoints_the_project(admin_client, prompt_tree, config_path):
    response = admin_client.post(
        "/admin/api/prompts/de/explainer/fork", json={"project": "Car Configurator"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["agent"] == "explainer__car-configurator"
    assert (prompt_tree / "de/explainer__car-configurator/prompt.yaml").is_file()
    written = config_path.read_text(encoding="utf-8")
    assert "de/explainer__car-configurator/prompt.yaml" in written


def test_a_fork_whose_config_write_fails_removes_what_it_created(
    admin_client, prompt_tree, monkeypatch
):
    def explode(path, text):
        raise HTTPException(status_code=400, detail="no")

    monkeypatch.setattr("testbench_ai_service.webui.routes.write_atomic", explode)

    response = admin_client.post("/admin/api/prompts/de/explainer/fork", json={"project": "Proj"})
    assert response.status_code == 400
    assert not (prompt_tree / "de/explainer__proj").exists()


def test_a_fork_whose_file_write_fails_removes_the_directory_and_unblocks_a_retry(
    admin_client, prompt_tree, monkeypatch
):
    """Important 1: write_all (copying the fork's own files) sat OUTSIDE the
    try/rollback, so a failure there left an empty target directory behind --
    build_fork refuses to fork into a directory that already exists, so every
    later retry would 409 forever until an operator deleted it by hand.
    """

    def explode(files, deletes=()):
        raise HTTPException(status_code=400, detail="disk full")

    monkeypatch.setattr("testbench_ai_service.webui.routes.write_all", explode)

    response = admin_client.post("/admin/api/prompts/de/explainer/fork", json={"project": "Proj"})
    assert response.status_code == 400
    assert not (prompt_tree / "de/explainer__proj").exists()

    monkeypatch.undo()
    retry = admin_client.post("/admin/api/prompts/de/explainer/fork", json={"project": "Proj"})
    assert retry.status_code == 200


def test_a_fork_refuses_a_non_admin(client, login):
    login(roles=["Project User"])
    # See test_the_plan_route_refuses_a_non_admin: the CSRF header must be
    # present so the 403 can only come from require_admin.
    response = client.post(
        "/admin/api/prompts/de/explainer/fork", json={"project": "P"}, headers=csrf(client)
    )
    assert response.status_code == 403


def test_a_fork_refuses_a_missing_csrf_header(client, login):
    login(roles=["Administrator"])
    response = client.post("/admin/api/prompts/de/explainer/fork", json={"project": "P"})
    assert response.status_code == 403


def test_a_fork_producing_an_unloadable_config_removes_what_it_created(
    admin_client, prompt_tree, monkeypatch
):
    """Ruling P1's other failure path: validation runs AFTER the files exist."""

    def invalid(edits, config_path, running):
        return (
            PreviewResponse(
                valid=False,
                issues=[
                    ConfigIssue(
                        path="projects.Proj",
                        message="nope",
                        toml_section="[testbench-ai-service.projects.Proj]",
                    )
                ],
                diffs=[],
                restart_required=[],
                in_flight_tasks=0,
                toml="",
            ),
            "",
            True,
        )

    monkeypatch.setattr("testbench_ai_service.webui.routes._plan_change", invalid)

    response = admin_client.post("/admin/api/prompts/de/explainer/fork", json={"project": "Proj"})
    assert response.status_code == 422
    assert not (prompt_tree / "de/explainer__proj").exists()
