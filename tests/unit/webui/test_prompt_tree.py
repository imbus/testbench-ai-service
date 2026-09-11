import textwrap

import pytest

from testbench_ai_service.webui.prompts import build_tree

VALID = textwrap.dedent(
    """
    name: "Erklärer"
    default_model: "gpt-5.5"
    default_variant: "A"
    variants:
      - name: "A"
        messages:
          - role: "system"
            text: "hallo"
    """
).strip()


@pytest.fixture
def prompts_dir(tmp_path):
    for lang in ("de", "en"):
        agent = tmp_path / lang / "explainer"
        agent.mkdir(parents=True)
        (agent / "prompt.yaml").write_text(VALID, encoding="utf-8")
    return tmp_path


def test_lists_every_language(prompts_dir):
    tree = build_tree(prompts_dir)
    assert [lang.lang for lang in tree.languages] == ["de", "en"]


def test_lists_the_agent_with_its_variants(prompts_dir):
    entry = build_tree(prompts_dir).languages[0].prompts[0]
    assert entry.agent == "explainer"
    assert entry.name == "Erklärer"
    assert entry.variants == ["A"]
    assert entry.ok is True


def test_the_file_is_relative_to_prompts_dir(prompts_dir):
    entry = build_tree(prompts_dir).languages[0].prompts[0]
    assert entry.file == "de/explainer/prompt.yaml"


def test_a_broken_prompt_is_listed_as_not_ok(prompts_dir):
    (prompts_dir / "de" / "explainer" / "prompt.yaml").write_text(": not yaml", encoding="utf-8")
    entry = build_tree(prompts_dir).languages[0].prompts[0]
    assert entry.ok is False
    assert entry.error
    assert entry.variants == []


def test_a_broken_prompt_does_not_hide_the_others(prompts_dir):
    broken = prompts_dir / "de" / "broken"
    broken.mkdir()
    (broken / "prompt.yaml").write_text("name: [unclosed", encoding="utf-8")
    agents = {e.agent for e in build_tree(prompts_dir).languages[0].prompts}
    assert agents == {"explainer", "broken"}


def test_a_directory_without_a_prompt_yaml_is_skipped(prompts_dir):
    (prompts_dir / "de" / "not_an_agent").mkdir()
    agents = {e.agent for e in build_tree(prompts_dir).languages[0].prompts}
    assert agents == {"explainer"}


def test_loose_files_at_the_top_level_are_not_languages(prompts_dir):
    (prompts_dir / "prompt.schema.json").write_text("{}", encoding="utf-8")
    assert [lang.lang for lang in build_tree(prompts_dir).languages] == ["de", "en"]


def test_a_missing_prompts_dir_is_an_empty_tree(tmp_path):
    assert build_tree(tmp_path / "absent").languages == []
