from pathlib import Path

import pytest
import tomlkit
import tomllib
from fastapi import HTTPException

from testbench_ai_service.webui.config_io import read_config_file
from testbench_ai_service.webui.document import (
    apply_edits,
    load_document,
    render_document,
    service_table,
)
from testbench_ai_service.webui.edits import merge_edits

COMMENTED = """\
# Top-of-file note the operator wrote.
[testbench-ai-service]
# Which TestBench we talk to.
tb_server_url = "https://tb.example.com:9443/api/"
port = 8010

[testbench-ai-service.llm_config]
provider = "openai"  # trailing note
"""


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(COMMENTED, encoding="utf-8")
    return path


def test_untouched_document_round_trips_byte_for_byte(config_file: Path):
    """The baseline every other guarantee rests on."""
    assert render_document(load_document(config_file)) == COMMENTED


def test_editing_one_value_keeps_every_comment(config_file: Path):
    document = load_document(config_file)
    service_table(document)["port"] = 9999

    rendered = render_document(document)

    assert "port = 9999" in rendered
    assert "# Top-of-file note the operator wrote." in rendered
    assert "# Which TestBench we talk to." in rendered
    assert "# trailing note" in rendered


def test_absent_file_yields_an_empty_service_table(tmp_path: Path):
    """The service runs on defaults alone; the console must still be able to save."""
    document = load_document(tmp_path / "nothing.toml")

    assert service_table(document) == {}
    assert render_document(document).strip() == "[testbench-ai-service]"


def test_service_table_is_created_when_the_file_has_other_sections(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text('[tool.other]\nkey = "value"\n', encoding="utf-8")

    document = load_document(path)
    service_table(document)["port"] = 8010

    rendered = render_document(document)
    assert "[tool.other]" in rendered
    assert 'key = "value"' in rendered
    assert "[testbench-ai-service]" in rendered
    assert "port = 8010" in rendered


def test_invalid_toml_is_a_400(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text("this is = = not toml", encoding="utf-8")

    with pytest.raises(HTTPException) as exc:
        load_document(path)
    assert exc.value.status_code == 400


def test_service_table_returns_the_live_table_not_a_copy(config_file: Path):
    """Callers mutate what service_table hands back; a copy would silently no-op."""
    document = load_document(config_file)
    service_table(document)["new_key"] = "new_value"

    assert 'new_key = "new_value"' in render_document(document)


def test_inline_table_section_keeps_all_keys_after_promotion(tmp_path: Path):
    """Inline table is promoted to regular table, preserving operator's keys."""
    path = tmp_path / "config.toml"
    path.write_text(
        "testbench-ai-service = { port = 8010, debug = true }\n",
        encoding="utf-8",
    )

    document = load_document(path)
    table = service_table(document)

    assert table["port"] == 8010
    assert table["debug"] is True

    rendered = render_document(document)
    assert "[testbench-ai-service]" in rendered
    assert "port = 8010" in rendered
    assert "debug = true" in rendered

    # Verify re-parse still has the keys
    re_parsed = load_document(tmp_path / "config.toml")
    re_parsed_table = re_parsed.get("testbench-ai-service")
    assert isinstance(re_parsed_table, dict)
    assert re_parsed_table["port"] == 8010
    assert re_parsed_table["debug"] is True


def test_can_write_nested_table_after_inline_promotion(tmp_path: Path):
    """After promoting inline table, can write nested sub-tables."""
    path = tmp_path / "config.toml"
    path.write_text(
        "testbench-ai-service = { port = 8010 }\n",
        encoding="utf-8",
    )

    document = load_document(path)
    table = service_table(document)
    # This should work after promotion; would fail with an inline table.
    table["llm_config"] = tomlkit.table()
    table["llm_config"]["provider"] = "openai"

    rendered = render_document(document)
    assert "[testbench-ai-service]" in rendered
    assert "port = 8010" in rendered
    assert "[testbench-ai-service.llm_config]" in rendered
    assert 'provider = "openai"' in rendered


def test_scalar_at_service_key_raises_400(tmp_path: Path):
    """A scalar value at the service key is an error, not silently replaced."""
    path = tmp_path / "config.toml"
    path.write_text("testbench-ai-service = 5\n", encoding="utf-8")

    document = load_document(path)
    with pytest.raises(HTTPException) as exc:
        service_table(document)
    assert exc.value.status_code == 400


def test_dotted_key_form_survives(tmp_path: Path):
    """Dotted key form (testbench-ai-service.port = ...) already works; keep it working."""
    path = tmp_path / "config.toml"
    path.write_text(
        "testbench-ai-service.port = 8010\ntestbench-ai-service.debug = true\n",
        encoding="utf-8",
    )

    document = load_document(path)
    table = service_table(document)

    assert table["port"] == 8010
    assert table["debug"] is True

    rendered = render_document(document)
    assert "testbench-ai-service.port = 8010" in rendered or (
        "[testbench-ai-service]" in rendered and "port = 8010" in rendered
    )
    assert "testbench-ai-service.debug = true" in rendered or (
        "[testbench-ai-service]" in rendered and "debug = true" in rendered
    )


@pytest.fixture
def interleaved_config_file(tmp_path: Path) -> Path:
    """Config with interleaved tables (triggers OutOfOrderTableProxy)."""
    path = tmp_path / "config.toml"
    path.write_text(
        "[testbench-ai-service]\n"
        "# operator note\n"
        "port = 8010\n"
        "\n"
        "[tool.other]\n"
        "x = 1\n"
        "\n"
        "[testbench-ai-service.llm_config]\n"
        'provider = "openai"\n',
        encoding="utf-8",
    )
    return path


def test_interleaved_comment_survives_after_write(interleaved_config_file: Path):
    """Operator's comment is preserved when section is out-of-order (OutOfOrderTableProxy)."""
    document = load_document(interleaved_config_file)
    service_table(document)["debug"] = True

    rendered = render_document(document)

    # Comment must survive
    assert "# operator note" in rendered
    # New key must be present
    assert "debug = true" in rendered or "debug = True" in rendered


def test_interleaved_other_sections_survive(interleaved_config_file: Path):
    """Interleaved [tool.other] table and its content survive intact."""
    document = load_document(interleaved_config_file)
    service_table(document)["debug"] = True

    rendered = render_document(document)

    assert "[tool.other]" in rendered
    assert "x = 1" in rendered


def test_interleaved_existing_keys_survive_and_reparses(
    interleaved_config_file: Path,
) -> None:
    """Existing keys in interleaved section survive and re-parse correctly."""
    document = load_document(interleaved_config_file)
    table = service_table(document)
    table["new_key"] = "new_value"

    rendered = render_document(document)

    # Write to disk to test re-parse
    interleaved_config_file.write_text(rendered, encoding="utf-8")

    # Re-parse and verify
    re_parsed = load_document(interleaved_config_file)
    re_parsed_table = re_parsed.get("testbench-ai-service")
    assert re_parsed_table["port"] == 8010
    assert re_parsed_table["new_key"] == "new_value"
    re_parsed_llm = re_parsed_table.get("llm_config")
    assert re_parsed_llm is not None
    assert re_parsed_llm["provider"] == "openai"


def test_interleaved_nested_table_write_preserves_comment(
    interleaved_config_file: Path,
) -> None:
    """Writing nested table through proxy preserves comments and renders valid TOML."""
    document = load_document(interleaved_config_file)
    table = service_table(document)
    table["logging"] = tomlkit.table()
    table["logging"]["level"] = "debug"

    rendered = render_document(document)

    # Comment must survive
    assert "# operator note" in rendered
    # New nested table must be present and valid
    assert "[testbench-ai-service.logging]" in rendered
    assert 'level = "debug"' in rendered
    # Original nested table must survive
    assert "[testbench-ai-service.llm_config]" in rendered
    assert 'provider = "openai"' in rendered


def test_apply_edits_changes_a_scalar_and_keeps_the_comments(config_file: Path):
    document = load_document(config_file)

    apply_edits(document, {"port": 9999})

    rendered = render_document(document)
    assert "port = 9999" in rendered
    assert "# Which TestBench we talk to." in rendered
    assert "# trailing note" in rendered


def test_apply_edits_reaches_a_nested_table(config_file: Path):
    document = load_document(config_file)

    apply_edits(document, {"llm_config.provider": "anthropic"})

    rendered = render_document(document)
    assert 'provider = "anthropic"' in rendered
    # tomlkit keeps the trailing comment attached to the value it annotated.
    assert "# trailing note" in rendered


def test_apply_edits_creates_a_missing_nested_table(config_file: Path):
    document = load_document(config_file)

    apply_edits(document, {"logging.file.log_level": "DEBUG"})

    rendered = render_document(document)
    assert "[testbench-ai-service.logging.file]" in rendered
    assert 'log_level = "DEBUG"' in rendered


def test_apply_edits_removes_a_key_on_none(config_file: Path):
    document = load_document(config_file)

    apply_edits(document, {"port": None})

    rendered = render_document(document)
    assert "port" not in rendered
    assert "# Top-of-file note the operator wrote." in rendered


def test_apply_edits_removing_an_absent_key_is_a_no_op(config_file: Path):
    document = load_document(config_file)

    apply_edits(document, {"llm_config.model": None})

    assert render_document(document) == COMMENTED


def test_apply_edits_writes_a_list_as_a_toml_array(config_file: Path):
    document = load_document(config_file)

    apply_edits(document, {"trusted_proxies": ["10.0.0.1", "10.0.0.2"]})

    rendered = render_document(document)
    assert 'trusted_proxies = ["10.0.0.1", "10.0.0.2"]' in rendered


def test_apply_edits_writes_a_project_name_that_needs_quoting(tmp_path: Path):
    """Project keys are TestBench project names: spaces, dots, anything."""
    path = tmp_path / "config.toml"
    path.write_text("[testbench-ai-service]\nport = 8010\n", encoding="utf-8")
    document = load_document(path)

    apply_edits(document, {"projects.My Project.language": "en"})

    rendered = render_document(document)
    assert 'language = "en"' in rendered
    # Re-parsing is the real assertion: the key must round-trip, however
    # tomlkit chose to quote it.
    reparsed = tomlkit.parse(rendered)
    assert reparsed["testbench-ai-service"]["projects"]["My Project"]["language"] == "en"


def test_apply_edits_is_idempotent(config_file: Path):
    first = load_document(config_file)
    apply_edits(first, {"port": 9999})
    once = render_document(first)

    second = load_document(config_file)
    apply_edits(second, {"port": 9999})
    apply_edits(second, {"port": 9999})

    assert render_document(second) == once


def test_apply_edits_result_reparses_to_the_merged_dict(config_file: Path):
    """The document path and the dict path must agree."""
    edits = {"port": 9999, "llm_config.model": "gpt-4.1", "logging.file.log_level": "DEBUG"}

    document = load_document(config_file)
    apply_edits(document, edits)
    from_document = tomlkit.parse(render_document(document))["testbench-ai-service"]

    from_dict = merge_edits(read_config_file(config_file), edits)

    assert dict(from_document) == from_dict


def test_apply_edits_and_merge_edits_agree_on_refusing_a_scalar_parent(tmp_path: Path):
    """Deviation 4: the document path and the dict path must also agree on
    what they refuse, not just on what they accept. A ``logging`` key that
    already holds a scalar cannot also hold a ``file`` sub-table."""
    path = tmp_path / "config.toml"
    path.write_text('[testbench-ai-service]\nlogging = "yes"\n', encoding="utf-8")
    document = load_document(path)
    edits = {"logging.file.log_level": "DEBUG"}

    with pytest.raises(HTTPException) as document_exc:
        apply_edits(document, edits)
    assert document_exc.value.status_code == 400

    with pytest.raises(HTTPException) as dict_exc:
        merge_edits({"logging": "yes"}, edits)
    assert dict_exc.value.status_code == 400


class TestQuotedPaths:
    """A project name is whatever TestBench calls the project.

    ``apply_edits`` writes what ``merge_edits`` validated, so both have to read
    an edit path the same way. When only ``merge_edits`` tokenized, a project
    whose name contains a dot previewed as valid and was written to the file as
    two nested tables under the wrong keys -- and its removal wrote nothing at
    all while reporting success.
    """

    def test_a_dotted_project_name_is_written_as_one_key(self, config_file: Path):
        document = load_document(config_file)

        apply_edits(document, {'projects."Release 2.0".language': "de"})

        written = tomllib.loads(render_document(document))
        projects = written["testbench-ai-service"]["projects"]
        assert projects == {"Release 2.0": {"language": "de"}}

    def test_a_dotted_project_name_can_be_removed_again(self, config_file: Path):
        document = load_document(config_file)
        apply_edits(document, {'projects."Release 2.0".language': "de"})

        apply_edits(document, {'projects."Release 2.0"': None})

        written = tomllib.loads(render_document(document))
        assert written["testbench-ai-service"].get("projects", {}) == {}

    def test_the_document_and_the_dict_agree_on_a_quoted_path(self, config_file: Path):
        """Preview shows the merged dict; apply writes the document."""
        edits = {'projects."Release 2.0".agents.reviewer.enabled': False}
        document = load_document(config_file)

        apply_edits(document, edits)

        merged = merge_edits(read_config_file(config_file), edits)
        assert tomllib.loads(render_document(document))["testbench-ai-service"] == merged
