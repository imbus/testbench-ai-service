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


def test_quote_key_with_literal_newline_produces_parseable_toml():
    """Regression guard for fix 2: control characters must be escaped.

    A project name containing a literal newline (which validate_edit_paths
    allows if it's not leading/trailing) must produce a TOML section that parses.
    Hand-rolled escaping missed control characters; tomlkit handles them correctly.
    """
    _, issues = validate_config_dict(
        {
            "tb_server_url": TB_URL,
            "projects": {"a\nb": {"language": "INVALID_LANGUAGE"}},
        }
    )

    assert issues
    # Must parse as valid TOML
    tomllib.loads(issues[0].toml_section + "\nx = 1\n")


def test_quote_key_with_literal_tab_produces_parseable_toml():
    """Regression guard: a project name with a tab must produce parseable TOML."""
    _, issues = validate_config_dict(
        {
            "tb_server_url": TB_URL,
            "projects": {"a\tb": {"language": "INVALID_LANGUAGE"}},
        }
    )

    assert issues
    tomllib.loads(issues[0].toml_section + "\nx = 1\n")


def test_quote_key_with_literal_carriage_return_produces_parseable_toml():
    """Regression guard: a project name with a carriage return must produce parseable TOML."""
    _, issues = validate_config_dict(
        {
            "tb_server_url": TB_URL,
            "projects": {"a\rb": {"language": "INVALID_LANGUAGE"}},
        }
    )

    assert issues
    tomllib.loads(issues[0].toml_section + "\nx = 1\n")


def test_bare_keys_remain_unquoted():
    """Regression guard for requirement 1: bare keys must not be quoted.

    A segment matching [A-Za-z0-9_-]+ must come back completely unquoted to
    keep the common case free of tomlkit and keep output identical to the
    fast path.
    """
    _, issues = validate_config_dict(
        {
            "tb_server_url": TB_URL,
            "logging": {"file": {"log_level": "INVALID_LEVEL"}},
        }
    )

    assert issues
    # The toml_section for logging.file.log_level should be [testbench-ai-service.logging.file]
    # with no quotes around logging or file
    assert issues[0].toml_section == "[testbench-ai-service.logging.file]"


def test_the_default_log_file_name_is_accepted():
    """Guards against over-rejection: a false positive here would block every
    apply that does not touch logging at all, since it inherits the default."""
    config, issues = validate_config_dict({"tb_server_url": TB_URL})

    assert issues == []
    assert config is not None


def test_a_log_path_in_a_writable_directory_is_accepted(tmp_path):
    config, issues = validate_config_dict(
        {
            "tb_server_url": TB_URL,
            "logging": {"file": {"file_name": str(tmp_path / "svc.log")}},
        }
    )

    assert issues == []
    assert config is not None


def test_an_empty_log_file_name_is_rejected():
    """Path("").parent resolves to ".", the writable current directory, so the
    empty case needs its own check or it would wrongly pass."""
    _, issues = validate_config_dict(
        {"tb_server_url": TB_URL, "logging": {"file": {"file_name": "   "}}}
    )

    assert [issue.path for issue in issues] == ["logging.file.file_name"]


def test_a_log_path_whose_directory_is_missing_is_addressed_to_its_field(tmp_path):
    """Spec 6.3: the console must refuse a config the service could not boot
    with. setup_logging()'s RotatingFileHandler creates the file but never a
    missing directory, so this must be caught here, before any write."""
    bad_path = tmp_path / "does-not-exist" / "svc.log"

    _, issues = validate_config_dict(
        {"tb_server_url": TB_URL, "logging": {"file": {"file_name": str(bad_path)}}}
    )

    assert [issue.path for issue in issues] == ["logging.file.file_name"]
    assert issues[0].toml_section == "[testbench-ai-service.logging.file]"
