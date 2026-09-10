"""``GET /prompts/{lang}/{agent}/meta`` -- read-only prompt metadata.

The endpoint is what makes the agent-detail form's ``variant`` a select rather
than typo-prone free text, and what gives each ``vars`` entry a widget matching
its declared ``value_type``. It reads files under ``prompts_dir`` on request, so
containment (``resolve_within``) is tested through all three request-controlled
segments: ``{lang}``, ``{agent}`` and ``?file=``.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from testbench_ai_service.config import AppConfig
from testbench_ai_service.main import create_app
from testbench_ai_service.webui.prompts import (
    declared_prompt_file,
    read_prompt_meta,
    resolve_prompt_file,
)

TB_URL = "https://localhost:9443/api/"

REVIEWER_PROMPT = """\
name: "Reviewer"
summary: "Reviews a test case set"
description: "A longer description."
default_model: "gpt-5.5"
default_variant: "Thorough"
variants:
  - name: "Thorough"
    description: "The careful one."
    model: "gpt-5.5"
    vars:
      max_findings:
        name: "Maximum findings"
        description: "How many findings to report at most."
        value_type: "number"
        default_value: 10
        required: false
      tone:
        name: "Tone"
        value_type: "enum"
        choices: ["formal", "casual"]
        required: true
    messages:
      - role: "system"
        text: "You review test cases. At most {{ vars.max_findings }}."
  - name: "Quick"
    messages:
      - role: "user"
        text: "Review briefly."
"""

OTHER_PROMPT = """\
name: "Project override"
default_model: "gpt-5.5"
default_variant: "Only"
variants:
  - name: "Only"
    messages:
      - role: "user"
        text: "Overridden."
"""


@pytest.fixture
def prompts_dir(tmp_path: Path) -> Path:
    """A prompts tree shaped like the packaged one: <lang>/<agent>/prompt.yaml."""
    root = tmp_path / "prompts"
    for lang in ("de", "en"):
        for agent in ("test_case_set_reviewer", "test_case_set_describer", "defect_explainer"):
            target = root / lang / agent / "prompt.yaml"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(REVIEWER_PROMPT, encoding="utf-8")
    (root / "de" / "test_case_set_reviewer" / "override.yaml").write_text(
        OTHER_PROMPT, encoding="utf-8"
    )
    return root


@pytest.fixture
def outsider(tmp_path: Path) -> Path:
    """A readable YAML file OUTSIDE prompts_dir, for the traversal tests."""
    path = tmp_path / "outside.yaml"
    path.write_text(OTHER_PROMPT, encoding="utf-8")
    return path


@pytest.fixture
def app(prompts_dir: Path, tmp_path: Path):
    with (
        patch("testbench_ai_service.config.validate_tb_server_url"),
        patch("testbench_ai_service.main.LLMFactory") as factory_cls,
    ):
        instance = MagicMock()
        instance.init_clients = MagicMock()
        instance.close_clients = AsyncMock()
        factory_cls.return_value = instance
        app = create_app(AppConfig(tb_server_url=TB_URL, prompts_dir=prompts_dir))
    app.state.config_path = tmp_path / "config.toml"
    return app


@pytest.fixture
def client(app):
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def signed_in(client, tb_connection):
    def _login(roles=None):
        if roles is not None:
            tb_connection.read_user_roles.return_value = roles
        with patch("testbench_ai_service.webui.auth.TBConnection", return_value=tb_connection):
            return client.post(
                "/admin/api/session", json={"username": "a.mueller", "password": "pw"}
            )

    return _login


def _meta(client, lang="de", agent="test_case_set_reviewer", **params):
    return client.get(f"/admin/api/prompts/{lang}/{agent}/meta", params=params)


# --- auth ----------------------------------------------------------------


def test_meta_without_a_session_is_401(client):
    assert _meta(client).status_code == 401


def test_meta_is_open_to_a_non_admin(client, signed_in):
    """A read, like GET /config: the form has to render for anyone signed in,
    even though only an admin can apply what they type into it."""
    signed_in(roles=["ProjectUser"])
    assert _meta(client).status_code == 200


# --- the happy path -----------------------------------------------------


def test_meta_reports_the_prompt_header(client, signed_in):
    signed_in()
    body = _meta(client).json()
    assert body["name"] == "Reviewer"
    assert body["summary"] == "Reviews a test case set"
    assert body["description"] == "A longer description."
    assert body["default_model"] == "gpt-5.5"
    assert body["default_variant"] == "Thorough"


def test_meta_lists_every_variant_in_file_order(client, signed_in):
    """The order is what populates the variant select, and the file's order is
    the only one the prompt author controls."""
    signed_in()
    assert [v["name"] for v in _meta(client).json()["variants"]] == ["Thorough", "Quick"]


def test_meta_declares_each_variable_with_its_type(client, signed_in):
    signed_in()
    thorough = _meta(client).json()["variants"][0]
    max_findings = thorough["vars"]["max_findings"]
    assert max_findings["value_type"] == "number"
    assert max_findings["name"] == "Maximum findings"
    assert max_findings["description"] == "How many findings to report at most."
    assert max_findings["default_value"] == 10
    assert max_findings["required"] is False


def test_meta_carries_the_choices_of_an_enum_variable(client, signed_in):
    """Without these the console cannot render an enum as a select, which is
    the whole reason the endpoint exists (design D7)."""
    signed_in()
    tone = _meta(client).json()["variants"][0]["vars"]["tone"]
    assert tone["choices"] == ["formal", "casual"]
    assert tone["required"] is True


def test_meta_reports_a_variant_that_declares_no_variables_as_empty(client, signed_in):
    signed_in()
    assert _meta(client).json()["variants"][1]["vars"] == {}


def test_meta_leaves_a_variant_without_its_own_model_unresolved(client, signed_in):
    """The variant's model is reported as declared, ``null`` included; the
    fallback to ``default_model`` is the console's to display, and flattening it
    here would hide that the variant does not pin a model at all."""
    signed_in()
    assert _meta(client).json()["variants"][1]["model"] is None


def test_meta_carries_no_message_bodies(client, signed_in):
    """Metadata only. Message templates are phase 4's editor, and the system
    prompt is not something a read endpoint should hand out by accident."""
    signed_in()
    response = _meta(client)
    assert "messages" not in response.json()["variants"][0]
    assert "You review test cases" not in response.text


def test_meta_resolves_the_language_segment(client, signed_in):
    """One endpoint serves both scopes; the caller names the effective language
    so a project's ``language`` override reads that project's prompt files."""
    signed_in()
    assert _meta(client, lang="en").status_code == 200


# --- which file ---------------------------------------------------------


def test_meta_reads_the_prompt_file_the_agent_key_declares(client, signed_in):
    signed_in()
    assert _meta(client, agent="defect_explainer").status_code == 200


def test_an_unknown_agent_key_is_404(client, signed_in):
    signed_in()
    assert _meta(client, agent="no_such_agent").status_code == 404


def test_the_file_parameter_overrides_the_agent_prompt_file(client, signed_in):
    """A project that points an agent at a different prompt must be edited
    against *that* file's variants. Resolving the global file instead is a
    wrong-metadata bug with no symptom until the agent runs."""
    signed_in()
    body = _meta(client, file="test_case_set_reviewer/override.yaml").json()
    assert body["name"] == "Project override"
    assert [v["name"] for v in body["variants"]] == ["Only"]


def test_the_file_parameter_is_honoured_for_an_unknown_agent_key(client, signed_in):
    """The draft may point at a prompt for an agent the on-disk config does not
    declare yet; the named file is enough to answer."""
    signed_in()
    response = _meta(client, agent="not_declared", file="test_case_set_reviewer/override.yaml")
    assert response.status_code == 200
    assert response.json()["name"] == "Project override"


def test_the_agent_prompt_file_comes_from_the_config_on_disk(client, signed_in, app):
    """The forms show the on-disk values, so metadata must be resolved from the
    same place -- otherwise a hand-edited config.toml the process has not taken
    up yet renders against the wrong file."""
    Path(app.state.config_path).write_text(
        "[testbench-ai-service.agents.test_case_set_reviewer.prompt]\n"
        'file = "test_case_set_reviewer/override.yaml"\n',
        encoding="utf-8",
    )
    signed_in()
    assert _meta(client).json()["name"] == "Project override"


# --- failure modes ------------------------------------------------------


def test_a_missing_prompt_file_is_404_not_500(client, signed_in, prompts_dir):
    """Risk 3: a prompts_dir that moved since boot must give a clean 404."""
    (prompts_dir / "de" / "test_case_set_reviewer" / "prompt.yaml").unlink()
    signed_in()
    assert _meta(client).status_code == 404


def test_an_unknown_language_is_404_not_500(client, signed_in):
    signed_in()
    assert _meta(client, lang="fr").status_code == 404


def test_a_prompt_file_that_is_not_valid_yaml_is_not_a_500(client, signed_in, prompts_dir):
    (prompts_dir / "de" / "test_case_set_reviewer" / "prompt.yaml").write_text(
        "name: [unterminated\n", encoding="utf-8"
    )
    signed_in()
    response = _meta(client)
    assert response.status_code == 422
    assert "prompt" in response.json()["detail"].lower()


def test_a_prompt_file_missing_required_metadata_is_not_a_500(client, signed_in, prompts_dir):
    (prompts_dir / "de" / "test_case_set_reviewer" / "prompt.yaml").write_text(
        "name: 'No variants here'\n", encoding="utf-8"
    )
    signed_in()
    assert _meta(client).status_code == 422


def test_a_directory_where_a_prompt_file_should_be_is_404(client, signed_in, prompts_dir):
    target = prompts_dir / "de" / "test_case_set_reviewer" / "prompt.yaml"
    target.unlink()
    target.mkdir()
    signed_in()
    assert _meta(client).status_code == 404


def test_meta_is_404_when_no_prompts_dir_is_configured(prompts_dir, tmp_path, tb_connection):
    """Without a base directory there is nothing to contain a request-supplied
    path against, so the endpoint refuses to look rather than reading a path
    relative to the process's working directory."""
    with (
        patch("testbench_ai_service.config.validate_tb_server_url"),
        patch("testbench_ai_service.main.LLMFactory") as factory_cls,
    ):
        instance = MagicMock()
        instance.init_clients = MagicMock()
        instance.close_clients = AsyncMock()
        factory_cls.return_value = instance
        app = create_app(AppConfig(tb_server_url=TB_URL, prompts_dir=prompts_dir))
    app.state.config_path = tmp_path / "config.toml"
    app.state.config.prompts_dir = None
    with TestClient(app, raise_server_exceptions=False) as c:
        with patch("testbench_ai_service.webui.auth.TBConnection", return_value=tb_connection):
            c.post("/admin/api/session", json={"username": "a", "password": "pw"})
        assert _meta(c).status_code == 404


# --- containment --------------------------------------------------------


def test_a_traversing_language_segment_is_refused(client, signed_in):
    """Percent-encoded dot segments, because that is the only spelling that
    actually reaches the endpoint: a literal ``../..`` is normalised out of the
    URL before it is sent, and an encoded slash makes the path stop matching
    this route altogether (the SPA fallback answers it, having read nothing).
    """
    signed_in()
    response = client.get("/admin/api/prompts/%2e%2e/test_case_set_reviewer/meta")
    assert response.status_code == 400
    assert "outside" in response.json()["detail"].lower()


def test_resolve_refuses_a_language_segment_that_climbs_out(prompts_dir):
    """Asserted directly on the resolver as well: the containment check must not
    depend on how many dot segments a client can get past the router."""
    with pytest.raises(HTTPException) as exc:
        resolve_prompt_file(prompts_dir, "../../etc", "prompt.yaml")
    assert exc.value.status_code == 400


def test_resolve_prefers_the_language_directory(prompts_dir):
    resolved = resolve_prompt_file(prompts_dir, "de", "test_case_set_reviewer/prompt.yaml")
    assert resolved == (prompts_dir / "de" / "test_case_set_reviewer" / "prompt.yaml").resolve()


def test_resolve_falls_back_to_prompts_dir_itself(prompts_dir):
    """The runtime resolver (validators.resolve_prompt_file_path) searches
    prompts_dir/<lang>/<file> and then prompts_dir/<file>. Diverging from it
    would make the console 404 on a prompt the service boots with happily."""
    shared = prompts_dir / "shared.yaml"
    shared.write_text(OTHER_PROMPT, encoding="utf-8")
    assert resolve_prompt_file(prompts_dir, "de", "shared.yaml") == shared.resolve()


def test_resolve_accepts_an_absolute_path_inside_prompts_dir(prompts_dir):
    target = prompts_dir / "de" / "test_case_set_reviewer" / "prompt.yaml"
    assert resolve_prompt_file(prompts_dir, "de", str(target)) == target.resolve()


def test_declared_prompt_file_falls_back_to_the_running_config(app):
    """A config.toml with no [agents] block at all is the common case, and the
    built-in's prompt.file is still the right answer for it."""
    running = app.state.config
    assert declared_prompt_file("defect_explainer", {}, running) == Path(
        "defect_explainer/prompt.yaml"
    )


def test_declared_prompt_file_ignores_a_partial_block_that_omits_the_file(app):
    """The agents merge is per field: overriding only prompt.variant keeps the
    built-in's prompt.file, and this must resolve the same way."""
    on_disk = {"agents": {"defect_explainer": {"prompt": {"variant": "Kurz"}}}}
    assert declared_prompt_file("defect_explainer", on_disk, app.state.config) == Path(
        "defect_explainer/prompt.yaml"
    )


def test_declared_prompt_file_is_none_for_an_unknown_agent(app):
    assert declared_prompt_file("no_such_agent", {}, app.state.config) is None


def test_declared_prompt_file_tolerates_a_malformed_agents_table(app):
    """The on-disk dict is unvalidated TOML, so every level of it can be the
    wrong type. None of those shapes may 500 the endpoint."""
    running = app.state.config
    for on_disk in (
        {"agents": "nonsense"},
        {"agents": {"defect_explainer": 5}},
        {"agents": {"defect_explainer": {"prompt": "nonsense"}}},
        {"agents": {"defect_explainer": {"prompt": {"file": 5}}}},
        {"agents": {"defect_explainer": {"prompt": {"file": "  "}}}},
    ):
        assert declared_prompt_file("defect_explainer", on_disk, running) == Path(
            "defect_explainer/prompt.yaml"
        )


def test_a_traversing_file_parameter_is_refused(client, signed_in, outsider):
    """``?file=`` is the one segment carrying a whole relative path, so it is
    the most attractive traversal vector on this endpoint."""
    signed_in()
    response = _meta(client, file="../../../outside.yaml")
    assert response.status_code == 400
    assert "outside" in response.json()["detail"].lower()


def test_an_absolute_file_parameter_outside_prompts_dir_is_refused(client, signed_in, outsider):
    signed_in()
    response = _meta(client, file=str(outsider))
    assert response.status_code == 400


def test_an_empty_file_parameter_is_refused(client, signed_in):
    """``Path("")`` is ``Path(".")`` and resolves to the base directory itself,
    so an empty candidate must be rejected before it becomes "read the
    language directory"."""
    signed_in()
    assert _meta(client, file="").status_code == 400


def test_a_file_parameter_with_a_nul_byte_is_refused(client, signed_in):
    signed_in()
    assert _meta(client, file="prompt.yaml\x00.png").status_code == 400


def test_a_non_yaml_file_inside_prompts_dir_is_refused(client, signed_in, prompts_dir):
    """Containment alone would let ``?file=`` read any file under prompts_dir,
    which also holds Jinja templates. Prompt metadata lives in YAML, so that is
    all this endpoint will open."""
    (prompts_dir / "de" / "notes.txt").write_text("private", encoding="utf-8")
    signed_in()
    response = _meta(client, file="notes.txt")
    assert response.status_code == 400
    assert "private" not in response.text


def test_the_suffix_check_is_applied_to_the_resolved_path(client, signed_in, prompts_dir):
    """A string-based suffix check is defeated by a trailing dot or an NTFS
    stream name, which is why security.resolve_within's docstring says to check
    the resolved path instead."""
    signed_in()
    assert _meta(client, file="test_case_set_reviewer/prompt.yaml.").status_code == 400


class TestErrorsDoNotLeakTheFilesystem:
    """`/prompts/.../meta` is session-gated, not admin-gated (design D7).

    Every signed-in user reaches it, and `?file=` can be aimed at any YAML
    under `prompts_dir`, so a failure must name the file the operator wrote
    rather than the server's absolute path or the file's own contents.
    """

    def test_a_404_names_the_file_relative_to_prompts_dir(self, tmp_path):
        with pytest.raises(HTTPException) as exc:
            read_prompt_meta(tmp_path / "de" / "gone.yaml", tmp_path)

        assert exc.value.status_code == 404
        assert exc.value.detail == "No prompt file at de/gone.yaml"
        assert str(tmp_path) not in exc.value.detail

    def test_a_422_names_the_broken_fields_but_not_their_values(self, tmp_path):
        prompt = tmp_path / "secrets.yaml"
        prompt.write_text("name: 1\nsummary: s3cret-looking-value\n", encoding="utf-8")

        with pytest.raises(HTTPException) as exc:
            read_prompt_meta(prompt, tmp_path)

        assert exc.value.status_code == 422
        assert "secrets.yaml" in exc.value.detail
        assert "s3cret-looking-value" not in exc.value.detail
        assert str(tmp_path) not in exc.value.detail

    def test_a_yaml_error_says_where_without_quoting_the_line(self, tmp_path):
        prompt = tmp_path / "broken.yaml"
        prompt.write_text("name: [unterminated\nsummary: confidential\n", encoding="utf-8")

        with pytest.raises(HTTPException) as exc:
            read_prompt_meta(prompt, tmp_path)

        assert exc.value.status_code == 422
        assert "not valid YAML" in exc.value.detail
        assert "confidential" not in exc.value.detail
