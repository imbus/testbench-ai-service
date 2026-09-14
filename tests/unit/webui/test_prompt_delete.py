from pathlib import Path

import pytest
from fastapi import HTTPException

from testbench_ai_service.webui.models import (
    PromptMessageDoc,
    PromptSaveRequest,
    PromptVariantDoc,
)
from testbench_ai_service.webui.prompts import (
    build_write_set,
    resolve_prompt_file,
    resolve_template_target,
)

ON_DISK = """\
name: "X"
default_variant: "A"
default_model: "m"
variants:
  - name: "A"
    messages:
      - role: "system"
        file: "system.jinja"
      - role: "user"
        file: "user.jinja"
"""


@pytest.fixture
def prompt(tmp_path):
    agent = tmp_path / "de" / "explainer"
    agent.mkdir(parents=True)
    (agent / "prompt.yaml").write_text(ON_DISK, encoding="utf-8")
    (agent / "system.jinja").write_text("system body", encoding="utf-8")
    (agent / "user.jinja").write_text("user body", encoding="utf-8")
    return tmp_path


def save(messages):
    return PromptSaveRequest(
        name="X",
        default_model="m",
        default_variant="A",
        variants=[PromptVariantDoc(name="A", messages=messages)],
    )


def inline(text):
    return PromptMessageDoc(role="user", source="inline", file=None, content=text)


def external(ref, text):
    return PromptMessageDoc(role="system", source="file", file=ref, content=text)


def test_a_template_no_longer_referenced_is_deleted(prompt):
    path = prompt / "de/explainer/prompt.yaml"
    plan = build_write_set(save([external("system.jinja", "system body")]), path, prompt)
    assert plan.deletes == [prompt / "de/explainer/user.jinja"]


def test_a_template_still_referenced_is_not_deleted(prompt):
    path = prompt / "de/explainer/prompt.yaml"
    plan = build_write_set(
        save([external("system.jinja", "system body"), external("user.jinja", "user body")]),
        path,
        prompt,
    )
    assert plan.deletes == []


def test_a_template_shared_with_another_prompt_is_not_deleted(prompt):
    other = prompt / "de" / "other"
    other.mkdir()
    (other / "prompt.yaml").write_text(
        'name: "O"\ndefault_variant: "A"\ndefault_model: "m"\nvariants:\n  - name: "A"\n'
        '    messages:\n      - role: "user"\n        file: "../explainer/user.jinja"\n',
        encoding="utf-8",
    )
    path = prompt / "de/explainer/prompt.yaml"
    plan = build_write_set(save([external("system.jinja", "system body")]), path, prompt)
    assert plan.deletes == []


def test_a_template_shared_with_a_deeply_nested_prompt_is_not_deleted(prompt):
    """The tree scan walks the whole ``prompts_dir``, not just ``<lang>/<agent>``.

    A prompt at ``de/explainer/sub/prompt.yaml`` -- three levels deep -- is
    just as real a holder as one at the two-level shape; missing it would
    delete a file still in use.
    """
    nested = prompt / "de" / "explainer" / "sub"
    nested.mkdir()
    (nested / "prompt.yaml").write_text(
        'name: "N"\ndefault_variant: "A"\ndefault_model: "m"\nvariants:\n  - name: "A"\n'
        '    messages:\n      - role: "user"\n        file: "../user.jinja"\n',
        encoding="utf-8",
    )
    path = prompt / "de/explainer/prompt.yaml"
    plan = build_write_set(save([external("system.jinja", "system body")]), path, prompt)
    assert plan.deletes == []


def test_a_file_the_prompt_never_referenced_is_never_deleted(prompt):
    """The payload cannot nominate a file. Only what the DISK said counts."""
    stranger = prompt / "de/explainer/stranger.jinja"
    stranger.write_text("not ours", encoding="utf-8")
    path = prompt / "de/explainer/prompt.yaml"
    plan = build_write_set(save([external("system.jinja", "system body")]), path, prompt)
    assert stranger not in plan.deletes
    assert stranger.exists()


def test_an_unparseable_prompt_anywhere_skips_every_deletion(prompt):
    broken = prompt / "de" / "broken"
    broken.mkdir()
    (broken / "prompt.yaml").write_text("name: [unclosed", encoding="utf-8")

    path = prompt / "de/explainer/prompt.yaml"
    plan = build_write_set(save([external("system.jinja", "system body")]), path, prompt)
    assert plan.deletes == []
    assert plan.deletions_skipped is not None
    assert "de/broken/prompt.yaml" in plan.deletions_skipped
    # Fail-safe, not fail-closed: the save itself still goes through.
    assert path in plan.writes


def test_switching_a_message_to_inline_deletes_its_template(prompt):
    path = prompt / "de/explainer/prompt.yaml"
    plan = build_write_set(
        save([external("system.jinja", "system body"), inline("was a file")]), path, prompt
    )
    assert plan.deletes == [prompt / "de/explainer/user.jinja"]


def test_an_orphaned_template_that_is_not_utf8_is_kept_on_disk(prompt):
    """I3 belt: an unreadable ``file``-backed message's own 409 guard (see
    test_prompt_write_set.py) only fires while the message is still
    ``source: "file"``. Flipping it to ``"inline"`` walks around that guard
    entirely and orphans the template -- never delete a file the console
    could not read in the first place.
    """
    latin1 = prompt / "de/explainer/system.jinja"
    latin1.write_bytes("Du bist Prüfer".encode("latin-1"))
    path = prompt / "de/explainer/prompt.yaml"
    plan = build_write_set(
        save([inline("was a file"), external("user.jinja", "user body")]), path, prompt
    )
    assert latin1 not in plan.deletes
    assert plan.deletions_skipped is not None
    assert "system.jinja" in plan.deletions_skipped
    assert latin1.read_bytes() == "Du bist Prüfer".encode("latin-1")


def test_a_new_template_is_created_not_refused(prompt):
    path = prompt / "de/explainer/prompt.yaml"
    plan = build_write_set(
        save([external("system.jinja", "system body"), external("fresh.jinja", "new body")]),
        path,
        prompt,
    )
    target = prompt / "de/explainer/fresh.jinja"
    assert plan.writes[target] == "new body"
    assert target in plan.creates


def test_a_new_template_may_not_name_a_subdirectory(prompt):
    path = prompt / "de/explainer/prompt.yaml"
    with pytest.raises(HTTPException) as excinfo:
        build_write_set(save([external("sub/fresh.jinja", "body")]), path, prompt)
    assert excinfo.value.status_code == 400


def test_a_new_template_may_not_overwrite_an_unreferenced_file(prompt):
    (prompt / "de/explainer/stranger.jinja").write_text("not ours", encoding="utf-8")
    path = prompt / "de/explainer/prompt.yaml"
    with pytest.raises(HTTPException) as excinfo:
        build_write_set(
            save([external("system.jinja", "s"), external("stranger.jinja", "clobber")]),
            path,
            prompt,
        )
    assert excinfo.value.status_code == 409


def test_referencing_an_unreferenced_file_unchanged_is_allowed(prompt):
    """Design 3.6/D7 permit a message to point at an existing shared template.

    The 409 guards against one prompt CLOBBERING another's file, not against
    merely pointing at one: a message whose content already matches what is
    on disk changes nothing, so it must not be refused.
    """
    (prompt / "de/explainer/stranger.jinja").write_text("not ours", encoding="utf-8")
    path = prompt / "de/explainer/prompt.yaml"
    plan = build_write_set(
        save([external("system.jinja", "s"), external("stranger.jinja", "not ours")]),
        path,
        prompt,
    )
    assert prompt / "de/explainer/stranger.jinja" not in plan.writes


def test_a_new_template_must_carry_an_allowed_suffix(prompt):
    """A disallowed suffix is refused by ``build_write_set`` overall.

    This does NOT exercise ``resolve_template_target``'s own suffix guard:
    ``resolve_template_file`` checks the suffix before it checks existence, so
    a name like ``fresh.txt`` is refused there and never reaches the
    resolve-or-create fallback at all. See ``TestResolveTemplateTarget`` below
    for a direct test of ``resolve_template_target``'s guards.
    """
    path = prompt / "de/explainer/prompt.yaml"
    with pytest.raises(HTTPException) as excinfo:
        build_write_set(save([external("fresh.txt", "body")]), path, prompt)
    assert excinfo.value.status_code == 400


class TestResolveTemplateTarget:
    """Direct tests of ``resolve_template_target`` -- a published interface
    Tasks 6 and 11 consume directly, not only reachable through
    ``build_write_set``'s resolve-or-create fallback.
    """

    def test_a_disallowed_suffix_is_refused(self, prompt):
        with pytest.raises(HTTPException) as excinfo:
            resolve_template_target(prompt, prompt / "de/explainer/prompt.yaml", "fresh.txt")
        assert excinfo.value.status_code == 400

    def test_dotdot_is_refused(self, prompt):
        with pytest.raises(HTTPException) as excinfo:
            resolve_template_target(prompt, prompt / "de/explainer/prompt.yaml", "..")
        assert excinfo.value.status_code == 400

    def test_a_single_dot_is_refused(self, prompt):
        with pytest.raises(HTTPException) as excinfo:
            resolve_template_target(prompt, prompt / "de/explainer/prompt.yaml", ".")
        assert excinfo.value.status_code == 400

    def test_a_disguised_dot_dot_is_refused(self, prompt):
        """M5-a: Path("./..").parts == ("..",), so a raw-string check against
        {".", ".."} lets this through as a bogus single segment that resolves
        to the LANGUAGE directory -- outside the prompt's own directory,
        which design D7 forbids. Only the suffix allowlist happened to stop
        it before this was fixed to check the normalised parts instead.
        """
        for disguised in ("./..", ".//..", "././..", "..//"):
            with pytest.raises(HTTPException) as excinfo:
                resolve_template_target(prompt, prompt / "de/explainer/prompt.yaml", disguised)
            assert excinfo.value.status_code == 400, disguised

    def test_an_absolute_path_is_refused(self, prompt):
        absolute = str(prompt / "de/explainer/fresh.jinja")
        with pytest.raises(HTTPException) as excinfo:
            resolve_template_target(prompt, prompt / "de/explainer/prompt.yaml", absolute)
        assert excinfo.value.status_code == 400

    def test_a_multi_segment_name_is_refused(self, prompt):
        with pytest.raises(HTTPException) as excinfo:
            resolve_template_target(prompt, prompt / "de/explainer/prompt.yaml", "sub/fresh.jinja")
        assert excinfo.value.status_code == 400

    def test_an_empty_name_is_refused(self, prompt):
        with pytest.raises(HTTPException) as excinfo:
            resolve_template_target(prompt, prompt / "de/explainer/prompt.yaml", "")
        assert excinfo.value.status_code == 400

    def test_a_plain_allowed_name_resolves_in_the_prompts_own_directory(self, prompt):
        target = resolve_template_target(prompt, prompt / "de/explainer/prompt.yaml", "fresh.jinja")
        assert target == prompt / "de/explainer/fresh.jinja"


def test_a_relative_prompts_dir_does_not_break_deletion_planning(tmp_path, monkeypatch):
    """``prompts_dir`` need only ``exist()`` per config validation -- it is not
    required to be absolute -- while ``prompt_path`` is always resolved by a
    real caller (``resolve_prompt_file`` -> ``resolve_within`` ->
    ``Path.resolve()``). ``_plan_deletions`` must still compare the two
    correctly instead of raising ``ValueError`` from an unresolved
    ``relative_to``.
    """
    prompts_root = tmp_path / "prompts"
    agent = prompts_root / "de" / "explainer"
    agent.mkdir(parents=True)
    (agent / "prompt.yaml").write_text(ON_DISK, encoding="utf-8")
    (agent / "system.jinja").write_text("system body", encoding="utf-8")
    (agent / "user.jinja").write_text("user body", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    relative_prompts_dir = Path("prompts")
    path = resolve_prompt_file(relative_prompts_dir, "de", Path("explainer") / "prompt.yaml")
    assert path.is_absolute()  # what every real caller hands build_write_set

    plan = build_write_set(
        save([external("system.jinja", "system body")]), path, relative_prompts_dir
    )
    assert plan.deletes == [agent.resolve() / "user.jinja"]
