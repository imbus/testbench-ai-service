import pytest
import yaml
from fastapi import HTTPException

from testbench_ai_service.webui.models import (
    PromptMessageDoc,
    PromptSaveRequest,
    PromptVariantDoc,
)
from testbench_ai_service.webui.prompts import build_write_set


@pytest.fixture
def prompt(tmp_path):
    agent = tmp_path / "de" / "explainer"
    agent.mkdir(parents=True)
    (agent / "prompt.yaml").write_text("name: x", encoding="utf-8")
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
    files = build_write_set(
        request_with([inline("hallo")]), prompt / "de/explainer/prompt.yaml", prompt
    )
    assert set(files) == {prompt / "de/explainer/prompt.yaml"}
    parsed = yaml.safe_load(files[prompt / "de/explainer/prompt.yaml"])
    assert parsed["variants"][0]["messages"][0]["text"] == "hallo"


def test_a_file_message_writes_the_template_too(prompt):
    path = prompt / "de/explainer/prompt.yaml"
    files = build_write_set(request_with([external("system.jinja", "new body")]), path, prompt)
    assert files[prompt / "de/explainer/system.jinja"] == "new body"
    parsed = yaml.safe_load(files[path])
    assert parsed["variants"][0]["messages"][0]["file"] == "system.jinja"
    assert "text" not in parsed["variants"][0]["messages"][0]


def test_the_yaml_carries_the_schema_header(prompt):
    (prompt / "prompt.schema.json").write_text("{}", encoding="utf-8")
    path = prompt / "de/explainer/prompt.yaml"
    files = build_write_set(request_with([inline("x")]), path, prompt)
    assert files[path].startswith("# yaml-language-server: $schema=../../prompt.schema.json")


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


def test_a_file_message_pointing_at_a_missing_file_is_refused(prompt):
    """4a never creates a file."""
    with pytest.raises(HTTPException) as e:
        build_write_set(
            request_with([external("absent.jinja", "body")]),
            prompt / "de/explainer/prompt.yaml",
            prompt,
        )
    assert e.value.status_code in (400, 404)


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
