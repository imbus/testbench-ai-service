from pathlib import Path

import pytest
import yaml
from fastapi import HTTPException

from testbench_ai_service.validators import resolve_prompt_file_path, validate_prompt_file
from testbench_ai_service.webui.fork import build_fork, rollback_fork, slugify_project

SOURCE = """\
name: "Reviewer"
default_variant: "A"
default_model: "m"
variants:
  - name: "A"
    messages:
      - role: "system"
        file: "system.jinja"
      - role: "user"
        text: "inline stays inline"
"""


@pytest.fixture
def tree(tmp_path):
    agent = tmp_path / "de" / "reviewer"
    agent.mkdir(parents=True)
    (agent / "prompt.yaml").write_text(SOURCE, encoding="utf-8")
    (agent / "system.jinja").write_bytes("grüße\r\n".encode("latin-1"))
    return tmp_path


def test_a_project_name_slugs_to_a_directory_segment():
    assert slugify_project("Car Configurator") == "car-configurator"
    assert slugify_project("Neues Projekt") == "neues-projekt"
    assert slugify_project("Release 2.0") == "release-2.0"
    assert slugify_project("   ") == ""


def test_the_fork_lands_beside_its_source(tree):
    plan = build_fork(
        tree, tree / "de/reviewer/prompt.yaml", "de", "reviewer", None, "Car Configurator"
    )
    assert plan.target_dir == tree / "de" / "reviewer__car-configurator"
    assert plan.agent_dir == "reviewer__car-configurator"


def test_the_config_value_carries_the_language_prefix(tree):
    plan = build_fork(tree, tree / "de/reviewer/prompt.yaml", "de", "reviewer", None, "Proj")
    assert plan.config_value == "de/reviewer__proj/prompt.yaml"


def test_templates_are_copied_as_bytes_under_their_basename(tree):
    plan = build_fork(tree, tree / "de/reviewer/prompt.yaml", "de", "reviewer", None, "Proj")
    copied = plan.target_dir / "system.jinja"
    assert plan.files[copied] == "grüße\r\n".encode("latin-1")


def test_the_forked_yaml_points_at_the_copied_basename(tree):
    plan = build_fork(tree, tree / "de/reviewer/prompt.yaml", "de", "reviewer", None, "Proj")
    document = yaml.safe_load(plan.files[plan.target_dir / "prompt.yaml"])
    messages = document["variants"][0]["messages"]
    assert messages[0]["file"] == "system.jinja"
    assert messages[1]["text"] == "inline stays inline"


def test_an_operator_supplied_directory_wins(tree):
    plan = build_fork(tree, tree / "de/reviewer/prompt.yaml", "de", "reviewer", "eigene", "Proj")
    assert plan.target_dir == tree / "de" / "eigene"
    assert plan.config_value == "de/eigene/prompt.yaml"


def test_an_existing_target_is_refused(tree):
    (tree / "de" / "reviewer__proj").mkdir()
    with pytest.raises(HTTPException) as excinfo:
        build_fork(tree, tree / "de/reviewer/prompt.yaml", "de", "reviewer", None, "Proj")
    assert excinfo.value.status_code == 409


def test_a_directory_escaping_prompts_dir_is_refused(tree):
    for bad in ("../escape", "a/b", "..", ""):
        with pytest.raises(HTTPException):
            build_fork(tree, tree / "de/reviewer/prompt.yaml", "de", "reviewer", bad, "Proj")


def test_two_templates_colliding_on_basename_are_refused(tree):
    shared = tree / "de" / "system.jinja"
    shared.write_text("other", encoding="utf-8")
    (tree / "de/reviewer/prompt.yaml").write_text(
        'name: "R"\ndefault_variant: "A"\ndefault_model: "m"\nvariants:\n  - name: "A"\n'
        '    messages:\n      - role: "system"\n        file: "system.jinja"\n'
        '      - role: "user"\n        file: "../system.jinja"\n',
        encoding="utf-8",
    )
    with pytest.raises(HTTPException) as excinfo:
        build_fork(tree, tree / "de/reviewer/prompt.yaml", "de", "reviewer", None, "Proj")
    assert excinfo.value.status_code == 409


def test_an_unreadable_source_template_refuses_the_fork(tree):
    (tree / "de/reviewer/system.jinja").unlink()
    with pytest.raises(HTTPException) as excinfo:
        build_fork(tree, tree / "de/reviewer/prompt.yaml", "de", "reviewer", None, "Proj")
    assert excinfo.value.status_code == 404


def test_rollback_removes_the_created_files_and_the_directory(tmp_path):
    target = tmp_path / "fork"
    target.mkdir()
    created = [target / "prompt.yaml", target / "system.jinja"]
    for path in created:
        path.write_text("x", encoding="utf-8")

    rollback_fork(created, target)

    assert not target.exists()


def test_the_config_value_resolves_through_both_resolvers_under_another_language(tree):
    """The whole point of the language prefix: it must survive resolution under
    a language that is NOT the fork's own -- both at boot (validate_prompt_file)
    and at runtime (resolve_prompt_file_path), since prompts_dir/<file> is each
    resolver's second candidate regardless of which language directory a fork
    actually sits in.
    """
    plan = build_fork(tree, tree / "de/reviewer/prompt.yaml", "de", "reviewer", None, "Proj")

    for path in plan.files:
        path.parent.mkdir(parents=True, exist_ok=True)
        content = plan.files[path]
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")

    resolved_boot = validate_prompt_file(Path(plan.config_value), prompts_dir=tree, language="en")
    assert resolved_boot == plan.target_dir / "prompt.yaml"

    resolved_runtime = resolve_prompt_file_path(
        Path(plan.config_value), prompts_dir=tree, language="en"
    )
    assert resolved_runtime == plan.target_dir / "prompt.yaml"
