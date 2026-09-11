from pathlib import Path

import yaml

from testbench_ai_service.webui.prompt_io import document_to_yaml, prune_none, schema_header

DOC = {
    "name": "Fehler-Erklärer",
    "summary": None,
    "default_model": "gpt-5.5",
    "default_variant": "A",
    "variants": [
        {
            "name": "A",
            "description": None,
            "model": None,
            "vars": {},
            "messages": [{"role": "system", "text": "Du bist ein Prüfer.\nZeile zwei."}],
        }
    ],
}


def test_key_order_is_preserved():
    text = document_to_yaml(DOC)
    assert text.index("name:") < text.index("default_model:") < text.index("variants:")


def test_none_valued_keys_are_dropped():
    text = document_to_yaml(DOC)
    assert "summary" not in text
    assert "null" not in text


def test_german_text_is_not_escaped():
    assert "Fehler-Erklärer" in document_to_yaml(DOC)
    assert "\\u" not in document_to_yaml(DOC)


def test_the_result_parses_back_to_the_same_document():
    assert yaml.safe_load(document_to_yaml(DOC)) == prune_none(DOC)


def test_the_schema_header_is_emitted_first():
    text = document_to_yaml(DOC, header="# yaml-language-server: $schema=../../prompt.schema.json")
    assert text.splitlines()[0] == "# yaml-language-server: $schema=../../prompt.schema.json"
    assert yaml.safe_load(text)["name"] == "Fehler-Erklärer"


def test_schema_header_is_relative_to_the_prompt(tmp_path):
    (tmp_path / "prompt.schema.json").write_text("{}", encoding="utf-8")
    prompt = tmp_path / "de" / "agent" / "prompt.yaml"
    prompt.parent.mkdir(parents=True)
    assert schema_header(prompt, tmp_path) == (
        "# yaml-language-server: $schema=../../prompt.schema.json"
    )


def test_no_schema_header_when_the_schema_is_absent(tmp_path):
    prompt = tmp_path / "de" / "agent" / "prompt.yaml"
    prompt.parent.mkdir(parents=True)
    assert schema_header(prompt, tmp_path) is None


def test_multiline_text_is_not_reflowed_into_one_line():
    text = document_to_yaml(DOC)
    assert "Zeile zwei." in text
    reloaded = yaml.safe_load(text)
    assert reloaded["variants"][0]["messages"][0]["text"] == "Du bist ein Prüfer.\nZeile zwei."


def test_every_repo_prompt_round_trips():
    """parse -> dump -> parse must reach the same document for real files."""
    for path in sorted(Path("testbench_ai_service/prompts").rglob("prompt.yaml")):
        original = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert yaml.safe_load(document_to_yaml(original)) == prune_none(original), path
