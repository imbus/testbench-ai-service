import pytest
import yaml
from fastapi import HTTPException

from testbench_ai_service.webui.models import (
    PromptMessageDoc,
    PromptSaveRequest,
    PromptVariantDoc,
)
from testbench_ai_service.webui.prompts import build_write_set

#: The prompt on disk before any save in this file. It must actually reference
#: system.jinja: Task 4 refuses a save that reuses an existing file this
#: prompt did not previously reference (design D9), so a stub that names no
#: variant at all would make every file-backed test below look like an
#: attempt to clobber a file the fixture happens to have written separately.
ON_DISK = """\
name: "x"
default_variant: "A"
default_model: "m"
variants:
  - name: "A"
    messages:
      - role: "system"
        file: "system.jinja"
"""


@pytest.fixture
def prompt(tmp_path):
    agent = tmp_path / "de" / "explainer"
    agent.mkdir(parents=True)
    (agent / "prompt.yaml").write_text(ON_DISK, encoding="utf-8")
    (agent / "system.jinja").write_text("old body", encoding="utf-8")
    return tmp_path


def request_with(messages, default_variant="A"):
    return PromptSaveRequest(
        name="Erklärer",
        default_model="gpt-5.5",
        default_variant=default_variant,
        variants=[PromptVariantDoc(name="A", messages=messages)],
    )


def inline(text):
    return PromptMessageDoc(role="user", source="inline", file=None, content=text)


def external(ref, text):
    return PromptMessageDoc(role="system", source="file", file=ref, content=text)


def test_an_inline_only_save_writes_just_the_yaml(prompt):
    plan = build_write_set(
        request_with([inline("hallo")]), prompt / "de/explainer/prompt.yaml", prompt
    )
    assert set(plan.writes) == {prompt / "de/explainer/prompt.yaml"}
    parsed = yaml.safe_load(plan.writes[prompt / "de/explainer/prompt.yaml"])
    assert parsed["variants"][0]["messages"][0]["text"] == "hallo"


def test_a_file_message_writes_the_template_too(prompt):
    path = prompt / "de/explainer/prompt.yaml"
    plan = build_write_set(request_with([external("system.jinja", "new body")]), path, prompt)
    assert plan.writes[prompt / "de/explainer/system.jinja"] == "new body"
    parsed = yaml.safe_load(plan.writes[path])
    assert parsed["variants"][0]["messages"][0]["file"] == "system.jinja"
    assert "text" not in parsed["variants"][0]["messages"][0]


def test_the_yaml_carries_the_schema_header(prompt):
    (prompt / "prompt.schema.json").write_text("{}", encoding="utf-8")
    path = prompt / "de/explainer/prompt.yaml"
    plan = build_write_set(request_with([inline("x")]), path, prompt)
    assert plan.writes[path].startswith("# yaml-language-server: $schema=../../prompt.schema.json")


def test_a_default_variant_naming_nothing_is_refused(prompt):
    with pytest.raises(HTTPException) as e:
        build_write_set(
            request_with([inline("x")], default_variant="Absent"),
            prompt / "de/explainer/prompt.yaml",
            prompt,
        )
    assert e.value.status_code == 422


def test_a_document_that_is_not_a_valid_prompt_is_refused(prompt):
    request = PromptSaveRequest(name="x", default_model="m", default_variant="A", variants=[])
    with pytest.raises(HTTPException) as e:
        build_write_set(request, prompt / "de/explainer/prompt.yaml", prompt)
    assert e.value.status_code == 422


def test_a_file_message_pointing_at_a_missing_file_is_created(prompt):
    """4b (this task, design D7) creates it instead: see test_prompt_delete.py
    for the full creation/deletion contract. 4a's "never creates a file" no
    longer holds -- creation is now confined to one path segment in the
    prompt's own directory rather than refused outright.
    """
    path = prompt / "de/explainer/prompt.yaml"
    plan = build_write_set(request_with([external("absent.jinja", "body")]), path, prompt)
    target = prompt / "de/explainer/absent.jinja"
    assert plan.writes[target] == "body"
    assert target in plan.creates


def test_a_file_message_escaping_prompts_dir_is_refused(prompt):
    with pytest.raises(HTTPException) as e:
        build_write_set(
            request_with([external("../../../evil.jinja", "body")]),
            prompt / "de/explainer/prompt.yaml",
            prompt,
        )
    assert e.value.status_code == 400


def test_nothing_is_written_to_disk_by_building_the_set(prompt):
    build_write_set(
        request_with([external("system.jinja", "new body")]),
        prompt / "de/explainer/prompt.yaml",
        prompt,
    )
    assert (prompt / "de/explainer/system.jinja").read_text(encoding="utf-8") == "old body"


def test_two_messages_giving_different_content_for_the_same_file_are_refused(prompt):
    request = PromptSaveRequest(
        name="Erklärer",
        default_model="gpt-5.5",
        default_variant="A",
        variants=[
            PromptVariantDoc(
                name="A",
                messages=[external("system.jinja", "FIRST"), inline("x")],
            ),
            PromptVariantDoc(
                name="B",
                messages=[external("system.jinja", "SECOND")],
            ),
        ],
    )
    with pytest.raises(HTTPException) as e:
        build_write_set(request, prompt / "de/explainer/prompt.yaml", prompt)
    assert e.value.status_code == 409


def test_two_messages_sharing_the_same_file_with_identical_content_is_fine(prompt):
    request = PromptSaveRequest(
        name="Erklärer",
        default_model="gpt-5.5",
        default_variant="A",
        variants=[
            PromptVariantDoc(
                name="A",
                messages=[external("system.jinja", "same body")],
            ),
            PromptVariantDoc(
                name="B",
                messages=[external("system.jinja", "same body")],
            ),
        ],
    )
    plan = build_write_set(request, prompt / "de/explainer/prompt.yaml", prompt)
    matching = [p for p in plan.writes if p == prompt / "de/explainer/system.jinja"]
    assert matching == [prompt / "de/explainer/system.jinja"]
    assert plan.writes[prompt / "de/explainer/system.jinja"] == "same body"


def test_a_variant_with_no_messages_is_refused(prompt):
    request = PromptSaveRequest(
        name="Erklärer",
        default_model="gpt-5.5",
        default_variant="A",
        variants=[PromptVariantDoc(name="A", messages=[])],
    )
    with pytest.raises(HTTPException) as e:
        build_write_set(request, prompt / "de/explainer/prompt.yaml", prompt)
    assert e.value.status_code == 422
    assert "A" in str(e.value.detail)


def test_an_unreadable_file_message_is_refused_rather_than_truncating_it(prompt):
    """C1: ``readable: false`` means the body is a placeholder, not the file.

    ``_message_doc`` answers ``content="", readable=False`` for a template it
    could not decode -- a legacy latin-1 file, say. Writing that back would
    leave the real file at zero bytes, silently, even for a save that only
    touched the prompt's name.
    """
    latin1 = prompt / "de/explainer/system.jinja"
    latin1.write_bytes("Du bist Prüfer".encode("latin-1"))
    message = PromptMessageDoc(
        role="system", source="file", file="system.jinja", content="", readable=False
    )
    with pytest.raises(HTTPException) as e:
        build_write_set(request_with([message]), prompt / "de/explainer/prompt.yaml", prompt)
    assert e.value.status_code == 409
    assert "system.jinja" in str(e.value.detail)
    # Names what to do next, the way _refuse_orphaned_variants does.
    assert "Repair the file on disk" in str(e.value.detail)
    assert latin1.read_bytes() == "Du bist Prüfer".encode("latin-1")


def test_an_unchanged_template_is_left_out_of_the_write_set(prompt):
    """I4: no change detection meant every referenced template was rewritten."""
    path = prompt / "de/explainer/prompt.yaml"
    plan = build_write_set(request_with([external("system.jinja", "old body")]), path, prompt)
    assert prompt / "de/explainer/system.jinja" not in plan.writes
    # The YAML itself did change, so it is still written.
    assert path in plan.writes


def test_an_untouched_crlf_template_is_not_rewritten_to_lf(prompt):
    """I4: the document loads a CRLF file as LF, so bytes alone are not enough."""
    template = prompt / "de/explainer/system.jinja"
    template.write_bytes(b"line one\r\nline two\r\n")
    plan = build_write_set(
        request_with([external("system.jinja", "line one\nline two\n")]),
        prompt / "de/explainer/prompt.yaml",
        prompt,
    )
    assert template not in plan.writes


def test_a_changed_crlf_template_is_still_written(prompt):
    template = prompt / "de/explainer/system.jinja"
    template.write_bytes(b"line one\r\nline two\r\n")
    plan = build_write_set(
        request_with([external("system.jinja", "line one\nline three\n")]),
        prompt / "de/explainer/prompt.yaml",
        prompt,
    )
    assert plan.writes[template] == "line one\nline three\n"


def test_an_unchanged_yaml_is_left_out_of_the_write_set(prompt):
    """A save that changes nothing at all writes nothing at all."""
    path = prompt / "de/explainer/prompt.yaml"
    request = request_with([inline("hallo")])
    first = build_write_set(request, path, prompt)
    path.write_text(first.writes[path], encoding="utf-8", newline="")
    assert build_write_set(request, path, prompt).writes == {}
