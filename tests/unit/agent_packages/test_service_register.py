from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from testbench_ai_service.agent_packages import loaded, service
from testbench_ai_service.agent_packages.manifest import load_manifest, site_dir, wheel_path
from testbench_ai_service.agent_packages.service import (
    DefaultDirs,
    FileConflicts,
    PackageConflict,
    PackageInvalid,
    PackageNotFound,
    RegisterAgent,
    activate_version,
    delete_version,
    register_agents,
    remove_package,
)
from testbench_ai_service.config import AppConfig
from testbench_ai_service.webui.config_io import read_config_file
from tests.helpers.packages import CLASS_PATH, PACKAGE, install_package, rater_report

TB_URL = "https://localhost:9443/api/"


@pytest.fixture(autouse=True)
def no_tb_server_probe():
    with patch("testbench_ai_service.config.validate_tb_server_url"):
        yield


class Env:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.prompts = root / "prompts"
        self.templates = root / "templates"
        self.packages = root / "packages"
        self.config_path = root / "config.toml"
        self.prompts.mkdir()
        self.templates.mkdir()
        self.config_path.write_text(
            "# operator comment: keep me\n"
            "[testbench-ai-service]\n"
            f'tb_server_url = "{TB_URL}"\n'
            f'prompts_dir = "{self.prompts.as_posix()}"\n'
            f'templates_dir = "{self.templates.as_posix()}"\n'
            "\n"
            "[testbench-ai-service.agent_packages]\n"
            f'dir = "{self.packages.as_posix()}"\n',
            encoding="utf-8",
        )

    def running(self) -> AppConfig:
        return AppConfig(**read_config_file(self.config_path))

    def agents(self) -> dict:
        agents: dict[str, Any] = read_config_file(self.config_path).get("agents", {})
        return agents

    def register(self, version: str = "1.0.0", key: str = "rater2", **kwargs):
        overwrite = kwargs.pop("overwrite", [])
        keep = kwargs.pop("keep", [])
        agents = kwargs.pop(
            "agents",
            [RegisterAgent(entry_point="acme_rater", agent_key=key, endpoint_path=f"/{key}")],
        )
        return register_agents(
            self.running(),
            self.config_path,
            PACKAGE,
            version,
            agents,
            overwrite=overwrite,
            keep=keep,
        )

    def existing(self, label: str, content: str = "mine") -> Path:
        """Create the file *label* (``prompts/…`` or ``templates/…``) with *content*."""
        kind, rest = label.split("/", 1)
        path = (self.prompts if kind == "prompts" else self.templates) / rest
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path


@pytest.fixture
def env(tmp_path) -> Env:
    return Env(tmp_path)


def test_register_refuses_default_dirs(env):
    install_package(env.packages, active=False)
    config = AppConfig(tb_server_url=TB_URL, agent_packages={"dir": env.packages})

    with pytest.raises(DefaultDirs):
        register_agents(
            config,
            env.config_path,
            PACKAGE,
            "1.0.0",
            [RegisterAgent(entry_point="acme_rater", agent_key="rater2", endpoint_path="/r")],
            overwrite=[],
        )


def test_register_writes_config_and_files(env):
    install_package(
        env.packages,
        active=False,
        report=rater_report(
            args_schema={
                "type": "object",
                "properties": {"limit": {"type": "integer", "default": 5}, "mode": {}},
            }
        ),
    )

    res = env.register()

    doc = env.agents()["rater2"]
    assert doc["package"] == PACKAGE
    assert doc["class_path"] == CLASS_PATH
    assert doc["endpoint_path"] == "/rater2"
    assert doc["enabled"] is True
    assert doc["prompt"]["file"] == "rater2/prompt.yaml"
    assert doc["args"] == {"limit": 5}
    assert (env.prompts / "en" / "rater2" / "prompt.yaml").exists()
    assert (env.prompts / "de" / "rater2" / "user.jinja").read_text() == "Rate {{ agent.title }}."
    assert (env.templates / "de" / "rater2" / "template.jinja").exists()
    assert "agents.rater2.class_path" in res.restart_required
    assert "agent_packages" in res.restart_required
    assert str(env.config_path.resolve()) in res.written
    assert load_manifest(env.packages).active(PACKAGE).version == "1.0.0"


def test_register_reports_conflicts_without_writing(env):
    install_package(env.packages, active=False)
    existing = env.prompts / "en" / "rater2" / "prompt.yaml"
    existing.parent.mkdir(parents=True)
    existing.write_text("mine", encoding="utf-8")
    config_before = env.config_path.read_text(encoding="utf-8")

    with pytest.raises(FileConflicts) as info:
        env.register()

    conflicts = info.value.conflicts
    assert [c.path for c in conflicts] == ["prompts/en/rater2/prompt.yaml"]
    assert conflicts[0].current == "mine"
    assert "Rater" in conflicts[0].incoming
    assert existing.read_text(encoding="utf-8") == "mine"
    assert not (env.prompts / "en" / "rater2" / "user.jinja").exists()
    assert env.config_path.read_text(encoding="utf-8") == config_before
    assert load_manifest(env.packages).active(PACKAGE) is None


def test_register_overwrites_listed_conflicts(env):
    install_package(env.packages, active=False)
    existing = env.templates / "en" / "rater2" / "started.jinja"
    existing.parent.mkdir(parents=True)
    existing.write_text("mine", encoding="utf-8")

    env.register(overwrite=["templates/en/rater2/started.jinja"])

    assert existing.read_text(encoding="utf-8") == "<p>started</p>"


STARTED = "templates/en/rater2/started.jinja"
FAILED = "templates/en/rater2/failed.jinja"


def test_register_keeps_listed_conflicts(env):
    install_package(env.packages, active=False)
    existing = env.existing(STARTED)

    env.register(keep=[STARTED])

    assert existing.read_text(encoding="utf-8") == "mine"
    assert (env.prompts / "en" / "rater2" / "prompt.yaml").exists()
    assert "rater2" in env.agents()


def test_register_mixes_kept_and_overwritten_files(env):
    install_package(env.packages, active=False)
    started = env.existing(STARTED)
    failed = env.existing(FAILED)

    env.register(keep=[STARTED], overwrite=[FAILED])

    assert started.read_text(encoding="utf-8") == "mine"
    assert failed.read_text(encoding="utf-8") != "mine"


def test_register_lists_every_undecided_conflict(env):
    install_package(env.packages, active=False)
    env.existing(STARTED)
    env.existing(FAILED)
    env.existing("prompts/en/rater2/prompt.yaml")

    with pytest.raises(FileConflicts) as info:
        env.register(keep=[STARTED])

    assert [c.path for c in info.value.conflicts] == ["prompts/en/rater2/prompt.yaml", FAILED]
    assert "rater2" not in env.agents()


def test_register_refuses_a_file_both_kept_and_overwritten(env):
    install_package(env.packages, active=False)
    env.existing(STARTED)

    with pytest.raises(PackageInvalid, match=r"started.jinja"):
        env.register(keep=[STARTED], overwrite=[STARTED])

    assert "rater2" not in env.agents()


def test_activate_keeps_listed_conflicts(env):
    install_package(env.packages, version="1.0.0", active=False)
    env.register()
    system = env.existing("prompts/en/rater2/system.jinja", "edited")
    install_package(env.packages, version="2.0.0", active=False)

    activate_version(
        env.running(),
        env.config_path,
        PACKAGE,
        "2.0.0",
        overwrite=[],
        keep=["prompts/en/rater2/system.jinja"],
    )

    assert system.read_text(encoding="utf-8") == "edited"
    assert load_manifest(env.packages).active(PACKAGE).version == "2.0.0"


def test_register_accepts_identical_existing_files(env):
    install_package(env.packages, active=False)
    existing = env.templates / "en" / "rater2" / "started.jinja"
    existing.parent.mkdir(parents=True)
    existing.write_text("<p>started</p>", encoding="utf-8")

    env.register()

    assert "rater2" in env.agents()


@pytest.mark.parametrize("key", ["test_case_set_reviewer", "rater2"])
def test_register_rejects_existing_key(env, key):
    install_package(env.packages, active=False)
    if key == "rater2":
        env.register()

    with pytest.raises(PackageConflict):
        env.register(key=key)


@pytest.mark.parametrize("path", ["/admin/api/agent-packages", "/admin/api/session", "/jobs/x"])
def test_register_rejects_an_endpoint_path_of_the_service(env, path):
    install_package(env.packages, active=False)

    with pytest.raises(PackageConflict, match="reserved"):
        env.register(
            agents=[RegisterAgent(entry_point="acme_rater", agent_key="rater2", endpoint_path=path)]
        )
    assert "rater2" not in read_config_file(env.config_path).get("agents", {})


def test_register_rejects_duplicate_keys_and_endpoints(env):
    install_package(env.packages, active=False)
    env.register()

    with pytest.raises(PackageConflict, match="endpoint"):
        env.register(
            agents=[
                RegisterAgent(entry_point="acme_rater", agent_key="other", endpoint_path="/rater2")
            ]
        )
    with pytest.raises(PackageConflict):
        env.register(
            agents=[
                RegisterAgent(entry_point="acme_rater", agent_key="a", endpoint_path="/a"),
                RegisterAgent(entry_point="acme_rater", agent_key="a", endpoint_path="/b"),
            ]
        )
    with pytest.raises(PackageConflict):
        env.register(
            agents=[
                RegisterAgent(entry_point="acme_rater", agent_key="a", endpoint_path="/x"),
                RegisterAgent(entry_point="acme_rater", agent_key="b", endpoint_path="/x"),
            ]
        )


def test_register_rejects_failed_entry_point(env):
    install_package(env.packages, active=False, report=rater_report(ok=False))

    with pytest.raises(PackageInvalid):
        env.register()
    with pytest.raises(PackageInvalid):
        env.register(agents=[RegisterAgent(entry_point="nope", agent_key="x", endpoint_path="/x")])


def test_register_rejects_a_failed_package(env):
    entry = install_package(env.packages, active=False)
    manifest = load_manifest(env.packages)
    report = manifest.packages[PACKAGE][entry.version].report
    report.ok = False
    # What the inspector writes for a failure of the package as a whole.
    report.errors = ["a top-level module clashes with the service's own"]
    service.save_manifest(env.packages, manifest)

    with pytest.raises(PackageInvalid, match="clashes"):
        env.register()


def test_register_refuses_while_another_version_is_active(env):
    install_package(env.packages, version="1.0.0")
    install_package(env.packages, version="2.0.0", active=False)

    with pytest.raises(PackageConflict):
        env.register(version="2.0.0")


def test_register_unknown_version(env):
    with pytest.raises(PackageNotFound):
        env.register()


def test_register_rolls_back_when_validation_fails(env):
    # The prompt uses agent.title, which the reported data fields do not offer.
    install_package(env.packages, active=False, report=rater_report(data_fields=["other"]))
    config_before = env.config_path.read_text(encoding="utf-8")

    with pytest.raises(PackageInvalid):
        env.register()

    assert env.config_path.read_text(encoding="utf-8") == config_before
    assert load_manifest(env.packages).active(PACKAGE) is None
    assert not (env.prompts / "en" / "rater2").exists()
    assert not (env.templates / "de" / "rater2").exists()


def test_register_rollback_restores_overwritten_files_and_backups(env):
    install_package(env.packages, active=False, report=rater_report(data_fields=["other"]))
    target_dir = env.templates / "en" / "rater2"
    target_dir.mkdir(parents=True)
    (target_dir / "started.jinja").write_text("mine", encoding="utf-8")
    (target_dir / "started.jinja.bak").write_text("older", encoding="utf-8")
    (target_dir / "failed.jinja").write_text("mine too", encoding="utf-8")

    with pytest.raises(PackageInvalid):
        env.register(
            overwrite=["templates/en/rater2/started.jinja", "templates/en/rater2/failed.jinja"]
        )

    assert sorted(p.name for p in target_dir.iterdir()) == [
        "failed.jinja",
        "started.jinja",
        "started.jinja.bak",
    ]
    assert (target_dir / "started.jinja").read_text(encoding="utf-8") == "mine"
    assert (target_dir / "started.jinja.bak").read_text(encoding="utf-8") == "older"
    assert (target_dir / "failed.jinja").read_text(encoding="utf-8") == "mine too"
    assert not (env.prompts / "en" / "rater2").exists()


def test_register_rolls_back_dirs_created_before_a_failing_mkdir(env, monkeypatch):
    install_package(env.packages, active=False)
    real_mkdir = Path.mkdir
    calls = {"count": 0}

    def flaky_mkdir(self, *args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 3:
            raise OSError("no more dirs")
        return real_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", flaky_mkdir)
    with pytest.raises(OSError, match="no more dirs"):
        env.register()
    monkeypatch.undo()

    assert list(env.prompts.iterdir()) == []
    assert list(env.templates.iterdir()) == []


def test_register_rolls_back_when_the_config_write_fails(env, monkeypatch):
    install_package(env.packages, active=False)
    config_before = env.config_path.read_text(encoding="utf-8")

    def boom(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(service, "write_atomic", boom)
    with pytest.raises(OSError, match="disk full"):
        env.register()

    assert env.config_path.read_text(encoding="utf-8") == config_before
    assert load_manifest(env.packages).active(PACKAGE) is None
    assert not (env.prompts / "en" / "rater2").exists()


def test_register_keeps_operator_comments(env):
    install_package(env.packages, active=False)

    env.register()

    assert "# operator comment: keep me" in env.config_path.read_text(encoding="utf-8")


def test_activate_switches_version_and_blocks_missing_entry_point(env):
    install_package(env.packages, version="1.0.0", active=False)
    env.register()
    install_package(env.packages, version="2.0.0", active=False, reports={})
    install_package(env.packages, version="3.0.0", active=False, report=rater_report(ok=False))
    install_package(env.packages, version="4.0.0", active=False)

    for broken in ("2.0.0", "3.0.0"):
        with pytest.raises(PackageInvalid):
            activate_version(env.running(), env.config_path, PACKAGE, broken, overwrite=[])
        assert load_manifest(env.packages).active(PACKAGE).version == "1.0.0"

    res = activate_version(env.running(), env.config_path, PACKAGE, "4.0.0", overwrite=[])

    assert load_manifest(env.packages).active(PACKAGE).version == "4.0.0"
    assert "agent_packages" in res.restart_required
    assert env.agents()["rater2"]["class_path"] == CLASS_PATH


def test_activate_updates_a_changed_class_path_and_copies_files(env):
    install_package(env.packages, version="1.0.0", active=False)
    env.register()
    (env.prompts / "en" / "rater2" / "system.jinja").write_text("edited", encoding="utf-8")
    moved = "acme.rater.agent.RaterAgent2"
    install_package(
        env.packages,
        version="2.0.0",
        active=False,
        report=rater_report(class_path=moved),
    )

    with pytest.raises(FileConflicts) as info:
        activate_version(env.running(), env.config_path, PACKAGE, "2.0.0", overwrite=[])
    assert [c.path for c in info.value.conflicts] == ["prompts/en/rater2/system.jinja"]
    assert load_manifest(env.packages).active(PACKAGE).version == "1.0.0"

    activate_version(
        env.running(),
        env.config_path,
        PACKAGE,
        "2.0.0",
        overwrite=["prompts/en/rater2/system.jinja"],
    )

    assert env.agents()["rater2"]["class_path"] == moved
    assert (env.prompts / "en" / "rater2" / "system.jinja").read_text() == (
        "You rate test case sets."
    )


def test_activate_after_remove_ignores_agents_of_the_stale_running_config(env):
    install_package(env.packages, version="1.0.0", active=False)
    env.register()
    stale = env.running()  # still has rater2 until the restart
    remove_package(stale, env.config_path, PACKAGE)
    install_package(
        env.packages,
        version="2.0.0",
        active=False,
        report=rater_report(class_path="acme.rater.agent.RaterAgent2"),
    )

    res = activate_version(stale, env.config_path, PACKAGE, "2.0.0", overwrite=[])

    assert load_manifest(env.packages).active(PACKAGE).version == "2.0.0"
    assert "rater2" not in env.agents()
    assert res.written == []


def test_remove_package_drops_agents_and_project_overrides(env):
    install_package(env.packages, active=False)
    env.register()
    with env.config_path.open("a", encoding="utf-8") as fh:
        fh.write('\n[testbench-ai-service.projects."My Project".agents.rater2]\nenabled = false\n')

    res = remove_package(env.running(), env.config_path, PACKAGE)

    data = read_config_file(env.config_path)
    assert "rater2" not in data.get("agents", {})
    assert "rater2" not in data.get("projects", {}).get("My Project", {}).get("agents", {})
    assert "# operator comment: keep me" in env.config_path.read_text(encoding="utf-8")
    manifest = load_manifest(env.packages)
    assert manifest.active(PACKAGE) is None
    assert "1.0.0" in manifest.packages[PACKAGE]  # versions stay until deleted
    assert (env.prompts / "en" / "rater2" / "prompt.yaml").exists()  # files stay
    assert "agents.rater2" in res.restart_required


def test_remove_unknown_package(env):
    with pytest.raises(PackageNotFound):
        remove_package(env.running(), env.config_path, PACKAGE)


def test_delete_active_version_conflicts(env):
    install_package(env.packages, version="1.0.0")

    with pytest.raises(PackageConflict):
        delete_version(env.packages, PACKAGE, "1.0.0")


def test_delete_loaded_version_conflicts(env, monkeypatch):
    install_package(env.packages, version="1.0.0", active=False)
    monkeypatch.setattr(loaded, "loaded_version", lambda name: "1.0.0")

    with pytest.raises(PackageConflict):
        delete_version(env.packages, PACKAGE, "1.0.0")


def test_delete_inactive_version_removes_files(env):
    install_package(env.packages, version="1.0.0")
    old = install_package(env.packages, version="0.9.0", active=False)

    delete_version(env.packages, PACKAGE, "0.9.0")

    manifest = load_manifest(env.packages)
    assert "0.9.0" not in manifest.packages[PACKAGE]
    assert not wheel_path(env.packages, old.filename).exists()
    assert not site_dir(env.packages, PACKAGE, "0.9.0").exists()
    assert site_dir(env.packages, PACKAGE, "1.0.0").is_dir()
    with pytest.raises(PackageNotFound):
        delete_version(env.packages, PACKAGE, "0.9.0")


def test_delete_last_version_drops_the_package(env):
    install_package(env.packages, version="1.0.0", active=False)

    delete_version(env.packages, PACKAGE, "1.0.0")

    assert PACKAGE not in load_manifest(env.packages).packages


def _rewrite_report(env, **changes) -> None:
    manifest = load_manifest(env.packages)
    stored = manifest.packages[PACKAGE]["1.0.0"]
    stored.report = stored.report.model_copy(update=changes)
    service.save_manifest(env.packages, manifest)


def test_register_works_beside_an_entry_point_that_failed_its_check(env):
    """One broken entry point rules out that one, not the whole package."""
    install_package(env.packages, active=False)
    broken = rater_report(
        entry_point="acme.broken:Missing", class_path="acme.broken.Missing", ok=False
    )
    broken.errors = ["cannot import 'acme.broken:Missing'"]
    _rewrite_report(env, ok=False, agents={"acme_rater": rater_report(), "acme_broken": broken})

    env.register()

    assert "rater2" in read_config_file(env.config_path)["agents"]
    with pytest.raises(PackageInvalid, match="not a usable agent"):
        env.register(
            agents=[RegisterAgent(entry_point="acme_broken", agent_key="b", endpoint_path="/b")]
        )


def test_register_is_refused_when_the_package_as_a_whole_failed(env):
    install_package(env.packages, active=False)
    _rewrite_report(env, ok=False, errors=["requires nosuchlib>=1, which is not installed"])

    with pytest.raises(PackageInvalid, match="failed the inspection: requires nosuchlib"):
        env.register()
    assert "rater2" not in read_config_file(env.config_path).get("agents", {})
