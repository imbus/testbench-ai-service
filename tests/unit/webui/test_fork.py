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


def test_a_slug_of_only_dots_or_dashes_is_empty():
    # Not just harmless -- "." / ".." must never come back as a bare directory
    # segment, even though every call site happens to prefix "<agent>__" today.
    assert slugify_project(".") == ""
    assert slugify_project("..") == ""
    assert slugify_project("...") == ""
    assert slugify_project("---") == ""


def test_a_name_with_no_latin_characters_slugs_to_empty():
    assert slugify_project("项目") == ""
    assert slugify_project("日本語プロジェクト") == ""
    assert slugify_project("Проект") == ""


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


def test_a_disguised_dot_dot_is_refused_with_400_not_409(tree):
    # Path("./..").parts == ("..",): pathlib collapses the leading "./" so a
    # naive check (len(parts) != 1 or raw_string in {".", ".."}) would let this
    # through as a bogus single segment resolving to prompts_dir itself -- which
    # then only 409s because prompts_dir happens to already exist. The status
    # code is the point: this must be a 400 (bad input), never a 409.
    for disguised in ("./..", ".//..", "././..", "..//"):
        with pytest.raises(HTTPException) as excinfo:
            build_fork(tree, tree / "de/reviewer/prompt.yaml", "de", "reviewer", disguised, "Proj")
        assert excinfo.value.status_code == 400, disguised


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
    detail = str(excinfo.value.detail)
    # The two sources share a basename -- that's *why* they collided -- so the
    # message must name the two distinct full paths, not repeat the basename
    # three times and tell the operator nothing about which files to rename.
    assert str(tree / "de" / "reviewer" / "system.jinja") in detail
    assert str(shared) in detail


def test_a_missing_source_template_refuses_the_fork_with_404(tree):
    (tree / "de/reviewer/system.jinja").unlink()
    with pytest.raises(HTTPException) as excinfo:
        build_fork(tree, tree / "de/reviewer/prompt.yaml", "de", "reviewer", None, "Proj")
    assert excinfo.value.status_code == 404
    # This is resolve_template_file's own 404 (raised before build_fork's
    # read_bytes is ever reached) -- unambiguously a different layer than the
    # try/except around read_bytes below, which is exercised separately.
    assert "No template file for" in str(excinfo.value.detail)


def test_an_unopenable_source_template_refuses_the_fork_with_404(tree, monkeypatch):
    # Distinct from the missing-file case above: this file EXISTS (is_file()
    # passes inside resolve_template_file) but read_bytes() itself raises --
    # e.g. a lock held by another process. Nothing else in the current test
    # suite reaches build_fork's own except OSError block; without this test,
    # deleting it would not fail anything.
    locked = tree / "de" / "reviewer" / "system.jinja"
    real_read_bytes = Path.read_bytes

    def fake_read_bytes(self):
        if self == locked:
            raise OSError("locked")
        return real_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", fake_read_bytes)

    with pytest.raises(HTTPException) as excinfo:
        build_fork(tree, tree / "de/reviewer/prompt.yaml", "de", "reviewer", None, "Proj")
    assert excinfo.value.status_code == 404
    assert "could not be read" in str(excinfo.value.detail)


def test_a_project_name_that_slugs_to_nothing_is_refused(tree):
    # design D5: silently forking every non-Latin-named project to the same
    # "reviewer__" directory would collide the second time with a 409 that
    # names nothing about the real cause. Refuse it up front instead.
    with pytest.raises(HTTPException) as excinfo:
        build_fork(
            tree, tree / "de/reviewer/prompt.yaml", "de", "reviewer", None, "日本語プロジェクト"
        )
    assert excinfo.value.status_code == 400


def test_an_explicit_directory_still_works_for_a_project_name_that_slugs_to_nothing(tree):
    plan = build_fork(
        tree, tree / "de/reviewer/prompt.yaml", "de", "reviewer", "eigene", "日本語プロジェクト"
    )
    assert plan.target_dir == tree / "de" / "eigene"


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
