import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
import tomllib

from testbench_ai_service.webui.validate import validate_config_dict

TB_URL = "https://localhost:9443/api/"


@pytest.fixture(autouse=True)
def no_url_probe():
    """validate_tb_server_url is about the URL's shape, not this module's job."""
    with patch("testbench_ai_service.config.validate_tb_server_url"):
        yield


def test_a_valid_config_returns_a_model_and_no_issues():
    config, issues = validate_config_dict({"tb_server_url": TB_URL, "port": 8010})

    assert issues == []
    assert config is not None
    assert config.port == 8010


def test_an_empty_config_is_valid_because_the_service_runs_on_defaults():
    config, issues = validate_config_dict({})

    assert issues == []
    assert config is not None


def test_a_wrong_type_is_addressed_to_the_field():
    _, issues = validate_config_dict({"tb_server_url": TB_URL, "port": "not a number"})

    assert len(issues) == 1
    assert issues[0].path == "port"
    assert issues[0].toml_section == "[testbench-ai-service]"
    assert issues[0].message


def test_no_model_is_returned_when_there_are_issues():
    config, issues = validate_config_dict({"port": "not a number"})

    assert config is None
    assert issues


def test_a_nested_failure_is_addressed_to_its_dotted_path():
    _, issues = validate_config_dict(
        {"tb_server_url": TB_URL, "logging": {"file": {"log_level": "LOUD"}}}
    )

    assert [issue.path for issue in issues] == ["logging.file.log_level"]
    assert issues[0].toml_section == "[testbench-ai-service.logging.file]"


def test_an_out_of_range_number_is_reported():
    _, issues = validate_config_dict({"tb_server_url": TB_URL, "tb_max_retries": -1})

    assert [issue.path for issue in issues] == ["tb_max_retries"]


def test_a_missing_ssl_file_is_reported_against_its_field():
    _, issues = validate_config_dict(
        {"tb_server_url": TB_URL, "ssl_cert": "/definitely/not/here.pem"}
    )

    assert [issue.path for issue in issues] == ["ssl_cert"]
    assert "not found" in issues[0].message


def test_every_failure_is_reported_not_just_the_first():
    _, issues = validate_config_dict({"port": "nope", "tb_max_retries": -1})

    assert {issue.path for issue in issues} == {"port", "tb_max_retries"}


def test_an_agent_failure_is_reported_rather_than_raising():
    _, issues = validate_config_dict(
        {
            "tb_server_url": TB_URL,
            "agents": {
                "test_case_set_reviewer": {
                    "enabled": True,
                    "endpoint_path": "/x",
                    "class_path": "nonexistent.module.Class",
                    "prompt": {"file": "test_case_set_reviewer/prompt.yaml"},
                }
            },
        }
    )

    assert issues


def test_a_non_dict_where_a_table_belongs_is_reported():
    _, issues = validate_config_dict({"llm_config": "not a table"})

    assert issues
    assert issues[0].path.startswith("llm_config")


def test_an_unexpected_error_becomes_a_root_issue():
    """A model validator can raise something that is not a ValidationError."""
    with patch(
        "testbench_ai_service.webui.validate.AppConfig",
        side_effect=RuntimeError("kaboom"),
    ):
        config, issues = validate_config_dict({})

    assert config is None
    assert len(issues) == 1
    assert issues[0].path == ""
    assert "kaboom" in issues[0].message


def test_an_array_element_error_is_addressed_to_the_array_section():
    """Regression guard for fix 2: trusted_proxies[2] error belongs to [testbench-ai-service].

    The array itself is a field inside the root section, not a sub-table.
    """
    _, issues = validate_config_dict(
        {"tb_server_url": TB_URL, "trusted_proxies": ["valid", "192.168.1.0/24", 123]}
    )

    assert issues
    assert issues[0].toml_section == "[testbench-ai-service]"


def test_quoted_keys_produce_valid_toml():
    """A project name with spaces must be quoted so the hint is valid TOML."""
    _, issues = validate_config_dict(
        {
            "tb_server_url": TB_URL,
            "projects": {"My Project": {"language": "INVALID_LANGUAGE"}},
        }
    )

    assert issues
    # The toml_section should be [testbench-ai-service.projects."My Project"]
    assert issues[0].toml_section == '[testbench-ai-service.projects."My Project"]'

    # It must parse as valid TOML (the operator can paste this as a hint into config.toml)
    tomllib.loads(issues[0].toml_section + "\nx = 1\n")


def test_escaped_quotes_in_keys_produce_valid_toml():
    """A project name with quotes must have them escaped in the TOML section."""
    _, issues = validate_config_dict(
        {
            "tb_server_url": TB_URL,
            "projects": {'Odd"Name': {"language": "INVALID_LANGUAGE"}},
        }
    )

    assert issues
    # The quotes must be escaped with backslash
    assert issues[0].toml_section == '[testbench-ai-service.projects."Odd\\"Name"]'

    # It must parse as valid TOML
    tomllib.loads(issues[0].toml_section + "\nx = 1\n")


def test_system_exit_from_an_imported_module_returns_a_root_issue():
    """Fix 1: a class_path whose module calls sys.exit() must not propagate.

    This repo's own utils/config.py calls sys.exit(), so validators that
    import modules can encounter it unexpectedly.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        # Create a module that calls sys.exit(1) at import time
        module_file = tmp_path / "exit_on_import.py"
        module_file.write_text("sys.exit(1)\n")

        # Monkeypatch sys.path so the module can be imported
        original_path = sys.path[:]
        try:
            sys.path.insert(0, str(tmp_path))

            config, issues = validate_config_dict(
                {
                    "tb_server_url": TB_URL,
                    "agents": {
                        "test_case_set_reviewer": {
                            "enabled": True,
                            "endpoint_path": "/x",
                            "class_path": "exit_on_import.SomeClass",
                            "prompt": {"file": "test_case_set_reviewer/prompt.yaml"},
                        }
                    },
                }
            )

            assert config is None
            assert len(issues) == 1
            assert issues[0].path == ""
        finally:
            sys.path[:] = original_path
