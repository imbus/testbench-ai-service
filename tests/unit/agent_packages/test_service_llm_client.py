"""Putting the LLM client of an uploaded package to use, and taking it out again."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from testbench_ai_service.agent_packages import loaded
from testbench_ai_service.agent_packages.manifest import load_manifest
from testbench_ai_service.agent_packages.service import (
    PackageConflict,
    PackageInvalid,
    PackageNotFound,
    RegisterAgent,
    activate_version,
    clear_llm_client,
    delete_version,
    package_llm_client,
    register_agents,
    remove_package,
    use_llm_client,
)
from testbench_ai_service.config import AppConfig
from testbench_ai_service.llm.routing import BUILTIN_ROUTING
from testbench_ai_service.webui.config_io import read_config_file
from tests.helpers.packages import LLM_CLASS_PATH, PACKAGE, install_package, llm_report
from tests.helpers.wheels import (
    VALID_AGENT_FILES,
    VALID_ENTRY_POINTS,
    VALID_LLM_CLIENT_FILES,
    VALID_LLM_ENTRY_POINTS,
)

TB_URL = "https://localhost:9443/api/"


@pytest.fixture(autouse=True)
def no_tb_server_probe():
    with patch("testbench_ai_service.config.validate_tb_server_url"):
        yield


@pytest.fixture(autouse=True)
def _reset_loaded():
    yield
    loaded.reset()


class Env:
    def __init__(self, root: Path, custom_dirs: bool = True, extra: str = "") -> None:
        self.packages = root / "packages"
        self.config_path = root / "config.toml"
        dirs = ""
        if custom_dirs:
            prompts, templates = root / "prompts", root / "templates"
            prompts.mkdir()
            templates.mkdir()
            dirs = (
                f'prompts_dir = "{prompts.as_posix()}"\n'
                f'templates_dir = "{templates.as_posix()}"\n'
            )
        self.config_path.write_text(
            "# operator comment: keep me\n"
            "[testbench-ai-service]\n"
            f'tb_server_url = "{TB_URL}"\n'
            f"{dirs}"
            "\n"
            "[testbench-ai-service.agent_packages]\n"
            f'dir = "{self.packages.as_posix()}"\n'
            f"{extra}",
            encoding="utf-8",
        )

    def running(self) -> AppConfig:
        return AppConfig(**read_config_file(self.config_path))

    def llm(self) -> dict[str, Any]:
        section: dict[str, Any] = read_config_file(self.config_path).get("llm_config", {})
        return section

    def install(self, version: str = "1.0.0", *, with_agent: bool = False, **kwargs):
        kwargs.setdefault("llm_clients", {"acme_llm": llm_report()})
        return install_package(
            self.packages,
            version=version,
            active=False,
            files={**VALID_AGENT_FILES, **VALID_LLM_CLIENT_FILES}
            if with_agent
            else VALID_LLM_CLIENT_FILES,
            entry_points=VALID_ENTRY_POINTS if with_agent else {},
            llm_entry_points=VALID_LLM_ENTRY_POINTS,
            reports=None if with_agent else {},
            **kwargs,
        )

    def use(self, version: str = "1.0.0", models=("acme-large",), **kwargs):
        return use_llm_client(
            self.running(),
            self.config_path,
            PACKAGE,
            version,
            kwargs.pop("entry_point", "acme_llm"),
            list(models),
            **kwargs,
        )

    def active(self) -> str | None:
        entry = load_manifest(self.packages).active(PACKAGE)
        return entry.version if entry else None


@pytest.fixture
def env(tmp_path) -> Env:
    return Env(tmp_path)


def test_use_writes_the_provider_and_activates_the_version(env):
    env.install()

    result = env.use(models=["acme-large", "acme-small"])

    assert env.llm() == {
        "provider": "custom",
        "class_path": LLM_CLASS_PATH,
        "package": PACKAGE,
        "extra_models": {
            "acme-large": {"provider": "custom", "routing": "fallback"},
            "acme-small": {"provider": "custom", "routing": "fallback"},
        },
    }
    assert env.active() == "1.0.0"
    assert "agent_packages" in result.restart_required
    assert "llm_config.package" in result.restart_required
    assert package_llm_client(read_config_file(env.config_path), PACKAGE) == LLM_CLASS_PATH


def test_use_keeps_the_rest_of_the_config_file(env):
    env.install()
    env.use()
    assert env.config_path.read_text(encoding="utf-8").startswith("# operator comment: keep me\n")


def test_use_does_not_need_own_prompt_directories(tmp_path):
    env = Env(tmp_path, custom_dirs=False)
    env.install()
    env.use()
    assert env.llm()["package"] == PACKAGE


def test_a_model_name_with_dots_slash_and_colon_stays_one_key(env):
    env.install()
    env.use(models=["meta/llama-3.1:70b"])
    assert env.llm()["extra_models"] == {
        "meta/llama-3.1:70b": {"provider": "custom", "routing": "fallback"}
    }
    env.running()  # the written file still validates


@pytest.mark.parametrize(
    "models",
    [
        [],
        ["gpt-acme"],
        ["o3-acme"],
        ["claude-acme"],
        [next(iter(BUILTIN_ROUTING))],
        ["has space"],
        ["acme-large", "acme-large"],
        ["ok-model", "gpt-acme"],
    ],
)
def test_use_refuses_models_that_would_never_reach_the_client(env, models):
    env.install()
    with pytest.raises(PackageInvalid):
        env.use(models=models)
    assert env.llm() == {}
    assert env.active() is None


def test_use_sets_the_default_model_when_asked(env):
    env.install()
    env.use(models=["acme-large", "acme-small"], default_model="acme-small")
    assert env.llm()["model"] == "acme-small"


def test_use_refuses_a_default_model_that_is_not_listed(env):
    env.install()
    with pytest.raises(PackageInvalid):
        env.use(models=["acme-large"], default_model="other")
    assert env.llm() == {}


def test_use_replaces_a_hand_written_custom_provider(tmp_path):
    env = Env(
        tmp_path,
        extra=(
            "\n[testbench-ai-service.llm_config]\n"
            'provider = "custom"\n'
            'class_path = "json.JSONDecoder"\n'
            "\n[testbench-ai-service.llm_config.extra_models]\n"
            'old-local = { provider = "custom", routing = "fallback" }\n'
            'tuned-model = { provider = "openai", routing = "chat" }\n'
        ),
    )
    env.install()

    env.use(models=["acme-large"])

    llm = env.llm()
    assert llm["class_path"] == LLM_CLASS_PATH
    assert llm["package"] == PACKAGE
    assert set(llm["extra_models"]) == {"acme-large", "tuned-model"}


def test_use_refuses_an_unknown_entry_point(env):
    env.install()
    with pytest.raises(PackageInvalid):
        env.use(entry_point="nope")
    assert env.active() is None


def test_use_refuses_a_client_that_failed_the_inspection(env):
    env.install(llm_clients={"acme_llm": llm_report(ok=False, errors=["broken"])})
    with pytest.raises(PackageInvalid):
        env.use()


def test_use_refuses_an_unknown_version(env):
    with pytest.raises(PackageNotFound):
        env.use()


def test_use_refuses_while_another_version_is_active(env):
    env.install("1.0.0")
    env.use()
    env.install("2.0.0")
    with pytest.raises(PackageConflict):
        env.use("2.0.0")
    assert env.active() == "1.0.0"


def test_using_again_replaces_the_models(env):
    env.install()
    env.use(models=["acme-large", "acme-small"])
    env.use(models=["acme-next"])
    assert set(env.llm()["extra_models"]) == {"acme-next"}


def test_clear_restores_the_defaults_and_deactivates_the_package(env):
    env.install()
    env.use(models=["acme-large", "acme-small"], default_model="acme-large")
    with env.config_path.open("a", encoding="utf-8") as fh:
        fh.write(
            "\n[testbench-ai-service.llm_config.agent_models]\n"
            'test_case_set_reviewer = "acme-small"\n'
            'other = "gpt-keep"\n'
        )

    result = clear_llm_client(env.running(), env.config_path, PACKAGE)

    assert env.llm() == {"agent_models": {"other": "gpt-keep"}}
    assert env.active() is None
    assert "agent_packages" in result.restart_required
    assert package_llm_client(read_config_file(env.config_path), PACKAGE) is None
    env.running()


def test_clear_keeps_a_package_with_registered_agents_active(env):
    env.install(with_agent=True)
    config = env.running()
    register_agents(
        config,
        env.config_path,
        PACKAGE,
        "1.0.0",
        [RegisterAgent(entry_point="acme_rater", agent_key="rater2", endpoint_path="/rater2")],
        overwrite=[],
    )
    env.use()

    clear_llm_client(env.running(), env.config_path, PACKAGE)

    assert env.active() == "1.0.0"
    assert "package" not in env.llm()


def test_clear_refuses_a_package_that_does_not_provide_the_client(env):
    env.install()
    with pytest.raises(PackageConflict):
        clear_llm_client(env.running(), env.config_path, PACKAGE)


def test_a_package_in_use_as_llm_client_cannot_be_removed(env):
    env.install()
    env.use()
    with pytest.raises(PackageConflict, match="LLM client"):
        remove_package(env.running(), env.config_path, PACKAGE)
    assert env.active() == "1.0.0"


def test_the_version_in_use_as_llm_client_cannot_be_deleted(env):
    env.install()
    env.use()
    with pytest.raises(PackageConflict):
        delete_version(env.packages, PACKAGE, "1.0.0")


def test_switching_to_a_version_without_the_client_is_refused(env):
    env.install("1.0.0")
    env.use()
    before = env.config_path.read_text(encoding="utf-8")
    env.install("2.0.0", llm_clients={})
    env.install("3.0.0", llm_clients={"acme_llm": llm_report(ok=False)})

    for broken in ("2.0.0", "3.0.0"):
        with pytest.raises(PackageInvalid):
            activate_version(env.running(), env.config_path, PACKAGE, broken, overwrite=[])
    assert env.active() == "1.0.0"
    assert env.config_path.read_text(encoding="utf-8") == before


def test_switching_versions_follows_a_moved_client_class(tmp_path):
    env = Env(tmp_path, custom_dirs=False)
    env.install("1.0.0")
    env.use()
    moved = "acme_llm.other.AcmeClient"
    env.install("2.0.0", llm_clients={"acme_llm": llm_report(class_path=moved)})

    activate_version(env.running(), env.config_path, PACKAGE, "2.0.0", overwrite=[])

    assert env.active() == "2.0.0"
    assert env.llm()["class_path"] == moved
