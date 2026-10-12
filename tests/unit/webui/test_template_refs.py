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
    """The case deletion safety actually turns on.

    Uses different valid spellings (absolute and relative) that resolve to the same
    file, verifying that deduplication is by resolved absolute path, not raw string.
    """
    shared = tree / "de" / "shared.jinja"
    shared.write_text("common", encoding="utf-8")
    # Alpha uses absolute path (forward-slash format), beta uses relative path.
    # Both resolve to the same file, testing deduplication by absolute path.
    (tree / "de/alpha/prompt.yaml").write_text(
        PROMPT.format(ref=shared.as_posix()), encoding="utf-8"
    )
    (tree / "de/beta/prompt.yaml").write_text(
        PROMPT.format(ref="../shared.jinja"), encoding="utf-8"
    )

    scan = scan_template_references(tree)
    assert scan.references[shared] == ["de/alpha/prompt.yaml", "de/beta/prompt.yaml"]


def test_an_unparseable_prompt_blocks_the_whole_scan(tree):
    (tree / "de/beta/prompt.yaml").write_text("name: [unclosed", encoding="utf-8")

    scan = scan_template_references(tree)
    assert scan.blocked_by == "de/beta/prompt.yaml"
    # Verify the corrupted prompt contributed zero references despite de/beta/system.jinja
    # existing on disk. Parsing failure must prevent message_refs from being called.
    assert scan.references == {tree / "de/alpha/system.jinja": ["de/alpha/prompt.yaml"]}


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


def test_a_prompt_whose_variants_is_a_mapping_blocks_deletions(tree):
    """I2: YAML-valid but not prompt-SHAPED must be treated like a parse
    failure, not like "references nothing" -- otherwise a template it still
    names looks orphaned and gets deleted.
    """
    (tree / "de/beta/prompt.yaml").write_text(
        'name: "X"\nvariants:\n  A:\n    messages: []\n', encoding="utf-8"
    )

    scan = scan_template_references(tree)
    assert scan.blocked_by == "de/beta/prompt.yaml"
    assert scan.references == {tree / "de/alpha/system.jinja": ["de/alpha/prompt.yaml"]}


def test_a_zero_byte_prompt_blocks_deletions(tree):
    """A zero-byte file parses to ``None``, not a dict -- just as blind a spot
    as a mapping-shaped ``variants``.
    """
    (tree / "de/beta/prompt.yaml").write_text("", encoding="utf-8")

    scan = scan_template_references(tree)
    assert scan.blocked_by == "de/beta/prompt.yaml"
    assert scan.references == {tree / "de/alpha/system.jinja": ["de/alpha/prompt.yaml"]}


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


def test_a_prompt_outside_the_lang_agent_shape_is_still_scanned(tree):
    """``resolve_prompt_file``'s ``prompts_dir/<file>`` fallback (and this
    repo's own ``config_example.toml`` project override) means a prompt can
    legitimately live somewhere other than ``<lang>/<agent>/prompt.yaml`` --
    here, one level up at ``prompts_dir/shared/prompt.yaml``. A scan that only
    walked two levels deep would never see this prompt at all, and a template
    it alone references would look orphaned.
    """
    shared_template = tree / "root.jinja"
    shared_template.write_text("root body", encoding="utf-8")
    holder = tree / "shared"
    holder.mkdir()
    (holder / "prompt.yaml").write_text(PROMPT.format(ref="../root.jinja"), encoding="utf-8")

    scan = scan_template_references(tree)
    assert scan.references[shared_template] == ["shared/prompt.yaml"]


def test_a_prompt_nested_deeper_than_lang_agent_is_still_scanned(tree):
    """A prompt at ``de/alpha/sub/prompt.yaml`` -- three levels deep -- is
    just as invisible to a two-level walk as one sitting one level too
    shallow.
    """
    nested = tree / "de" / "alpha" / "sub"
    nested.mkdir()
    nested_template = nested / "deep.jinja"
    nested_template.write_text("deep body", encoding="utf-8")
    (nested / "prompt.yaml").write_text(PROMPT.format(ref="deep.jinja"), encoding="utf-8")

    scan = scan_template_references(tree)
    assert scan.references[nested_template] == ["de/alpha/sub/prompt.yaml"]
