from pathlib import Path

import pytest
import tomlkit
from fastapi import HTTPException

from testbench_ai_service.webui.document import (
    load_document,
    render_document,
    service_table,
)

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
