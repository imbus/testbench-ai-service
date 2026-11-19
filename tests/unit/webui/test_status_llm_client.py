"""The status screen's note about an LLM client that comes from an uploaded package."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from testbench_ai_service.agent_packages import loaded
from testbench_ai_service.models.config import LLMConfig
from testbench_ai_service.webui.status import llm_client_error
from tests.helpers.packages import LLM_CLASS_PATH, PACKAGE, install_package, llm_report
from tests.helpers.wheels import VALID_LLM_CLIENT_FILES, VALID_LLM_ENTRY_POINTS


@pytest.fixture(autouse=True)
def _reset_loaded():
    yield
    loaded.reset()


def _config(**llm):
    return SimpleNamespace(llm_config=LLMConfig(**llm))


def _packaged():
    return _config(provider="custom", class_path=LLM_CLASS_PATH, package=PACKAGE)


def test_no_error_without_a_package_client():
    assert llm_client_error(_config()) is None


def test_a_package_that_is_not_loaded_asks_for_a_restart():
    assert "restart" in (llm_client_error(_packaged()) or "").lower()


def test_a_package_that_failed_to_load_gives_its_reason():
    loaded.mark_failed(PACKAGE, "the wheel 'x.whl' is missing")
    assert llm_client_error(_packaged()) == "the wheel 'x.whl' is missing"


def test_a_loaded_package_reports_the_client_failure(tmp_path):
    packages = tmp_path / "packages"
    install_package(
        packages,
        files=VALID_LLM_CLIENT_FILES,
        entry_points={},
        llm_entry_points=VALID_LLM_ENTRY_POINTS,
        reports={},
        llm_clients={"acme_llm": llm_report()},
    )
    loaded.activate_packages(packages)
    assert llm_client_error(_packaged()) is None
    loaded.mark_llm_client_failed("cannot import 'x'")
    assert llm_client_error(_packaged()) == "cannot import 'x'"


def test_a_stale_package_key_of_another_provider_is_ignored():
    assert llm_client_error(_config(provider="openai", package=PACKAGE)) is None
