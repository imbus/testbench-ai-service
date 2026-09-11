import textwrap

import pytest

from testbench_ai_service.webui.prompts import read_prompt_document

YAML = textwrap.dedent(
    """
    name: "Erklärer"
    summary: "kurz"
    default_model: "gpt-5.5"
    default_variant: "A"
    variants:
      - name: "A"
        model: "gpt-5.5"
        vars:
          tone:
            name: "Tonfall"
            value_type: "string"
        messages:
          - role: "system"
            file: "system.jinja"
          - role: "user"
            text: "Inline {{ agent.title }}"
    """
).strip()


@pytest.fixture
def prompt(tmp_path):
    agent = tmp_path / "de" / "explainer"
    agent.mkdir(parents=True)
    (agent / "prompt.yaml").write_text(YAML, encoding="utf-8")
    (agent / "system.jinja").write_text("Du bist {{ agent.role }}", encoding="utf-8")
    return tmp_path


def test_reads_the_header(prompt):
    doc = read_prompt_document(prompt / "de/explainer/prompt.yaml", prompt, "de", "explainer")
    assert doc.name == "Erklärer"
    assert doc.summary == "kurz"
    assert doc.default_variant == "A"
    assert doc.file == "de/explainer/prompt.yaml"


def test_an_inline_message_carries_its_text(prompt):
    doc = read_prompt_document(prompt / "de/explainer/prompt.yaml", prompt, "de", "explainer")
    inline = doc.variants[0].messages[1]
    assert inline.source == "inline"
    assert inline.file is None
    assert inline.content == "Inline {{ agent.title }}"
    assert inline.readable is True


def test_a_file_message_carries_the_file_contents(prompt):
    doc = read_prompt_document(prompt / "de/explainer/prompt.yaml", prompt, "de", "explainer")
    external = doc.variants[0].messages[0]
    assert external.source == "file"
    assert external.file == "system.jinja"
    assert external.content == "Du bist {{ agent.role }}"
    assert external.readable is True


def test_variable_declarations_survive(prompt):
    doc = read_prompt_document(prompt / "de/explainer/prompt.yaml", prompt, "de", "explainer")
    assert doc.variants[0].vars["tone"].value_type == "string"


def test_a_missing_template_is_readable_false_not_a_failure(prompt):
    (prompt / "de" / "explainer" / "system.jinja").unlink()
    doc = read_prompt_document(prompt / "de/explainer/prompt.yaml", prompt, "de", "explainer")
    external = doc.variants[0].messages[0]
    assert external.readable is False
    assert external.content == ""
    assert doc.variants[0].messages[1].content == "Inline {{ agent.title }}"


def test_a_template_escaping_prompts_dir_is_readable_false(prompt):
    path = prompt / "de" / "explainer" / "prompt.yaml"
    path.write_text(YAML.replace('"system.jinja"', '"../../../evil.jinja"'), encoding="utf-8")
    doc = read_prompt_document(path, prompt, "de", "explainer")
    assert doc.variants[0].messages[0].readable is False


def test_the_context_skeleton_covers_both_message_kinds(prompt):
    doc = read_prompt_document(prompt / "de/explainer/prompt.yaml", prompt, "de", "explainer")
    assert doc.agent_context_skeleton == {"role": "", "title": ""}
