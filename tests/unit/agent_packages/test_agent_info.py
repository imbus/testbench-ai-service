from __future__ import annotations

import sys
from pathlib import Path

import pytest

from testbench_ai_service.agent_packages import loaded
from testbench_ai_service.agent_packages.agent_info import AgentUnavailable, agent_info
from testbench_ai_service.models.config import AgentConfig, PromptConfig
from tests.helpers.packages import CLASS_PATH, PACKAGE, install_package, rater_report

REVIEWER = "testbench_ai_service.agents.test_case_set_reviewer.agent.TestCaseSetReviewer"


def cfg_agent(class_path: str = CLASS_PATH, package: str | None = PACKAGE) -> AgentConfig:
    return AgentConfig(
        enabled=True,
        endpoint_path="/acme",
        class_path=class_path,
        prompt=PromptConfig(file=Path("acme/prompt.yaml")),
        package=package,
    )


def test_agent_info_imports_a_built_in_agent(tmp_path):
    info = agent_info(cfg_agent(REVIEWER, package=None), tmp_path)

    assert info.agent_class is not None
    assert info.agent_class.__name__ == "TestCaseSetReviewer"
    assert "test_case_set" in info.data_fields
    assert info.context_sample["test_case_set"] == "<str>"


def test_agent_info_passes_import_errors_of_a_built_in_agent_through(tmp_path):
    with pytest.raises(ValueError, match="cannot import"):
        agent_info(cfg_agent("no.such.module.Agent", package=None), tmp_path)


def test_agent_info_uses_report_when_not_loaded(tmp_path):
    install_package(
        tmp_path,
        report=rater_report(
            data_fields=["foo"],
            step_fields={"plan": ["bar"]},
            args_schema={"type": "object"},
            context_sample={"foo": "<str>"},
        ),
    )

    info = agent_info(cfg_agent(), tmp_path)

    assert info.agent_class is None
    assert info.data_fields == ["foo"]
    assert info.step_fields == {"plan": ["bar"]}
    assert info.args_schema == {"type": "object"}
    assert info.context_sample == {"foo": "<str>"}
    assert "acme" not in sys.modules


def test_agent_info_finds_the_report_by_class_path(tmp_path):
    install_package(tmp_path, report=rater_report(class_path="acme.rater.agent.Other"))

    with pytest.raises(AgentUnavailable):
        agent_info(cfg_agent(), tmp_path)


def test_agent_info_without_active_version_is_unavailable(tmp_path):
    install_package(tmp_path, active=False)

    with pytest.raises(AgentUnavailable):
        agent_info(cfg_agent(), tmp_path)


def test_agent_info_without_manifest_is_unavailable(tmp_path):
    with pytest.raises(AgentUnavailable):
        agent_info(cfg_agent(), tmp_path / "missing")


def test_agent_info_imports_a_loaded_package(tmp_path):
    install_package(tmp_path)
    loaded.activate_packages(tmp_path)

    info = agent_info(cfg_agent(), tmp_path)

    assert info.agent_class is not None
    assert info.agent_class.__name__ == "RaterAgent"
    assert info.data_fields == ["title"]


def test_agent_info_uses_the_report_of_a_version_activated_after_startup(tmp_path):
    install_package(tmp_path)
    loaded.activate_packages(tmp_path)
    install_package(
        tmp_path,
        version="2.0.0",
        report=rater_report(class_path="acme.rater.agent.NewAgent", data_fields=["new"]),
    )

    info = agent_info(cfg_agent("acme.rater.agent.NewAgent"), tmp_path)

    assert info.agent_class is None
    assert info.data_fields == ["new"]
    assert loaded.failures() == {}


def test_agent_info_marks_a_failing_import_of_a_loaded_package(tmp_path):
    install_package(tmp_path)
    loaded.activate_packages(tmp_path)

    with pytest.raises(AgentUnavailable):
        agent_info(cfg_agent("acme.rater.agent.Missing"), tmp_path)

    assert PACKAGE in loaded.failures()
