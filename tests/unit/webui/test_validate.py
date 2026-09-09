from unittest.mock import patch

import pytest

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
