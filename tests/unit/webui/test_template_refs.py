import pytest

from testbench_ai_service.webui.template_refs import scan_template_references

PROMPT = """\
name: "X"
default_variant: "A"
default_model: "m"
variants:
  - name: "A"
    messages:
      - role: "system"
        file: "{ref}"
"""


@pytest.fixture
def tree(tmp_path):
    for lang, agent in (("de", "alpha"), ("de", "beta")):
        directory = tmp_path / lang / agent
        directory.mkdir(parents=True)
        (directory / "system.jinja").write_text("body", encoding="utf-8")
        (directory / "prompt.yaml").write_text(PROMPT.format(ref="system.jinja"), encoding="utf-8")
    return tmp_path


def test_each_prompt_is_recorded_against_the_template_it_references(tree):
    scan = scan_template_references(tree)
    assert scan.references[tree / "de/alpha/system.jinja"] == ["de/alpha/prompt.yaml"]
    assert scan.references[tree / "de/beta/system.jinja"] == ["de/beta/prompt.yaml"]
    assert scan.blocked_by is None


def test_a_template_outside_the_agent_directory_is_resolved(tree):
    shared = tree / "de" / "shared.jinja"
    shared.write_text("common", encoding="utf-8")
    (tree / "de/beta/prompt.yaml").write_text(
        PROMPT.format(ref="../shared.jinja"), encoding="utf-8"
    )

    scan = scan_template_references(tree)
    # Only beta points at it; alpha still uses its own system.jinja.
    assert scan.references[shared] == ["de/beta/prompt.yaml"]


def test_a_template_shared_by_two_prompts_lists_both(tree):
    """The case deletion safety actually turns on."""
    shared = tree / "de" / "shared.jinja"
    shared.write_text("common", encoding="utf-8")
    for agent in ("alpha", "beta"):
        (tree / "de" / agent / "prompt.yaml").write_text(
            PROMPT.format(ref="../shared.jinja"), encoding="utf-8"
        )

    scan = scan_template_references(tree)
    assert scan.references[shared] == ["de/alpha/prompt.yaml", "de/beta/prompt.yaml"]


def test_an_unparseable_prompt_blocks_the_whole_scan(tree):
    (tree / "de/beta/prompt.yaml").write_text("name: [unclosed", encoding="utf-8")

    scan = scan_template_references(tree)
    assert scan.blocked_by == "de/beta/prompt.yaml"


def test_a_schema_invalid_but_parseable_prompt_still_protects_its_templates(tree):
    # Parses as YAML, is not a valid PromptDefinition (no default_model). Its
    # reference must still count, or saving the OTHER prompt would delete a file
    # this one is using.
    (tree / "de/beta/prompt.yaml").write_text(
        'name: "X"\nvariants:\n  - name: "A"\n    messages:\n      - role: "user"\n'
        '        file: "system.jinja"\n',
        encoding="utf-8",
    )

    scan = scan_template_references(tree)
    assert scan.references[tree / "de/beta/system.jinja"] == ["de/beta/prompt.yaml"]
    assert scan.blocked_by is None


def test_a_reference_escaping_prompts_dir_is_ignored(tree):
    (tree / "de/beta/prompt.yaml").write_text(
        PROMPT.format(ref="../../../outside.jinja"), encoding="utf-8"
    )

    scan = scan_template_references(tree)
    assert all("outside" not in str(path) for path in scan.references)
    assert scan.blocked_by is None


def test_a_missing_prompts_dir_scans_to_nothing(tmp_path):
    scan = scan_template_references(tmp_path / "nope")
    assert scan.references == {}
    assert scan.blocked_by is None
