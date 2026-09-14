import pytest
from fastapi import HTTPException

from testbench_ai_service.webui.models import (
    PromptMessageDoc,
    PromptSaveRequest,
    PromptVariantDoc,
)
from testbench_ai_service.webui.prompts import build_write_set

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


def test_switching_a_message_to_inline_deletes_its_template(prompt):
    path = prompt / "de/explainer/prompt.yaml"
    plan = build_write_set(
        save([external("system.jinja", "system body"), inline("was a file")]), path, prompt
    )
    assert plan.deletes == [prompt / "de/explainer/user.jinja"]


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


def test_a_new_template_must_carry_an_allowed_suffix(prompt):
    path = prompt / "de/explainer/prompt.yaml"
    with pytest.raises(HTTPException) as excinfo:
        build_write_set(save([external("fresh.txt", "body")]), path, prompt)
    assert excinfo.value.status_code == 400
