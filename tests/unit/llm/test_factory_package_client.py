"""The custom LLM client of an uploaded package: created only from a loaded package."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI

from testbench_ai_service.agent_packages import loaded
from testbench_ai_service.llm.factory import LLMClientUnavailable, LLMFactory
from testbench_ai_service.main import init_services
from testbench_ai_service.models.config import LLMConfig
from tests.helpers.packages import LLM_CLASS_PATH, PACKAGE, install_package, llm_report
from tests.helpers.wheels import VALID_LLM_CLIENT_FILES, VALID_LLM_ENTRY_POINTS


@pytest.fixture(autouse=True)
def _reset_loaded():
    yield
    loaded.reset()


def _config(class_path: str = LLM_CLASS_PATH, **extra) -> LLMConfig:
    return LLMConfig(provider="custom", class_path=class_path, package=PACKAGE, **extra)


def _load(tmp_path, files=None) -> None:
    packages = tmp_path / "packages"
    install_package(
        packages,
        files=files or VALID_LLM_CLIENT_FILES,
        entry_points={},
        llm_entry_points=VALID_LLM_ENTRY_POINTS,
        reports={},
        llm_clients={"acme_llm": llm_report()},
    )
    assert loaded.activate_packages(packages) == []


def test_a_client_of_an_unloaded_package_is_unavailable():
    with pytest.raises(LLMClientUnavailable, match=PACKAGE):
        LLMFactory().get_client(_config())
    assert PACKAGE in (loaded.llm_client_failure() or "")


def test_an_unloaded_package_names_why_it_failed_to_load():
    loaded.mark_failed(PACKAGE, "the wheel 'x.whl' is missing")
    with pytest.raises(LLMClientUnavailable, match="is missing"):
        LLMFactory().get_client(_config())


def test_a_client_of_a_loaded_package_is_created_with_the_factory_arguments(tmp_path):
    _load(tmp_path)
    client = LLMFactory().get_client(_config(timeout=5.0, max_retries=2))
    assert type(client).__name__ == "AcmeClient"
    assert client.kwargs == {"timeout": 5.0, "max_retries": 2}
    assert loaded.llm_client_failure() is None


def test_a_class_the_loaded_package_does_not_have_is_unavailable(tmp_path):
    _load(tmp_path)
    with pytest.raises(LLMClientUnavailable, match="cannot import"):
        LLMFactory().get_client(_config("acme_llm.client.Missing"))
    assert "cannot import" in (loaded.llm_client_failure() or "")


def test_a_class_that_is_no_llm_client_is_unavailable(tmp_path):
    files = dict(VALID_LLM_CLIENT_FILES)
    files["acme_llm/other.py"] = "class NotAClient:\n    pass\n"
    _load(tmp_path, files)
    with pytest.raises(LLMClientUnavailable, match="not a subclass of LLMClient"):
        LLMFactory().get_client(_config("acme_llm.other.NotAClient"))


def test_loading_the_packages_again_forgets_the_client_failure(tmp_path):
    loaded.mark_llm_client_failed("old reason")
    loaded.activate_packages(tmp_path / "packages")
    assert loaded.llm_client_failure() is None


def test_the_service_starts_while_the_package_client_is_unavailable():
    app = FastAPI()
    app.state.config = SimpleNamespace(llm_config=_config())
    init_services(app)
    assert isinstance(app.state.llm_factory, LLMFactory)
    assert loaded.llm_client_failure() is not None
