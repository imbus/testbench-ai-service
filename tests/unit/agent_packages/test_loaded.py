from __future__ import annotations

import importlib
import sys

from testbench_ai_service.agent_packages import loaded
from testbench_ai_service.agent_packages.manifest import (
    load_manifest,
    manifest_path,
    save_manifest,
    site_dir,
)
from tests.helpers.packages import PACKAGE, install_package


def test_activate_packages_adds_site_dir(tmp_path):
    packages_dir = tmp_path / "packages"
    install_package(packages_dir)

    errors = loaded.activate_packages(packages_dir)

    assert errors == []
    assert sys.path[0] == str(site_dir(packages_dir, PACKAGE, "1.0.0"))
    assert loaded.is_loaded(PACKAGE)
    assert loaded.loaded_version(PACKAGE) == "1.0.0"
    assert "acme" not in sys.modules


def test_activate_packages_ignores_inactive_versions(tmp_path):
    packages_dir = tmp_path / "packages"
    install_package(packages_dir, active=False)

    assert loaded.activate_packages(packages_dir) == []
    assert not loaded.is_loaded(PACKAGE)
    assert loaded.loaded_version(PACKAGE) is None


def test_activate_packages_skips_hash_mismatch(tmp_path):
    packages_dir = tmp_path / "packages"
    install_package(packages_dir, sha256="00" * 32)
    site = str(site_dir(packages_dir, PACKAGE, "1.0.0"))

    errors = loaded.activate_packages(packages_dir)

    assert len(errors) == 1
    assert PACKAGE in errors[0]
    assert "hash" in errors[0]
    assert site not in sys.path
    assert not loaded.is_loaded(PACKAGE)
    assert PACKAGE in loaded.failures()


def test_activate_packages_skips_a_missing_site_dir(tmp_path):
    packages_dir = tmp_path / "packages"
    install_package(packages_dir)
    site = site_dir(packages_dir, PACKAGE, "1.0.0")
    for path in sorted(site.rglob("*"), reverse=True):
        path.unlink() if path.is_file() else path.rmdir()
    site.rmdir()

    errors = loaded.activate_packages(packages_dir)

    assert len(errors) == 1
    assert not loaded.is_loaded(PACKAGE)


def test_activate_packages_missing_dir(tmp_path):
    assert loaded.activate_packages(tmp_path / "missing") == []
    assert loaded.failures() == {}


def test_activate_packages_reports_an_unreadable_manifest(tmp_path):
    packages_dir = tmp_path / "packages"
    packages_dir.mkdir()
    manifest_path(packages_dir).write_text("{not json", encoding="utf-8")

    errors = loaded.activate_packages(packages_dir)

    assert len(errors) == 1
    assert "manifest" in errors[0].lower()


def test_mark_failed_unloads_nothing_but_is_listed(tmp_path):
    loaded.mark_failed(PACKAGE, "boom")

    assert loaded.failures() == {PACKAGE: "boom"}


def test_reset_removes_own_path_entries_and_failures(tmp_path):
    packages_dir = tmp_path / "packages"
    install_package(packages_dir)
    loaded.activate_packages(packages_dir)
    loaded.mark_failed("other", "boom")
    loaded.mark_agent_failed("acme", "boom")
    site = str(site_dir(packages_dir, PACKAGE, "1.0.0"))

    loaded.reset()

    assert site not in sys.path
    assert not loaded.is_loaded(PACKAGE)
    assert loaded.failures() == {}
    assert loaded.agent_failures() == {}


def test_mark_agent_failed_keeps_the_package_loaded(tmp_path):
    packages_dir = tmp_path / "packages"
    install_package(packages_dir)
    loaded.activate_packages(packages_dir)

    loaded.mark_agent_failed("acme", "boom")

    assert loaded.agent_failures() == {"acme": "boom"}
    assert loaded.is_loaded(PACKAGE)
    assert loaded.failures() == {}


def test_activate_packages_again_swaps_a_changed_version(tmp_path):
    """A restart in the same process must load the newly active version."""
    packages_dir = tmp_path / "packages"
    install_package(packages_dir)
    loaded.activate_packages(packages_dir)
    old_site = str(site_dir(packages_dir, PACKAGE, "1.0.0"))
    importlib.import_module("acme.rater.agent")  # from version 1.0.0

    install_package(packages_dir, version="2.0.0")
    errors = loaded.activate_packages(packages_dir)

    assert errors == []
    assert old_site not in sys.path
    assert sys.path[0] == str(site_dir(packages_dir, PACKAGE, "2.0.0"))
    assert loaded.loaded_version(PACKAGE) == "2.0.0"
    assert "acme.rater.agent" not in sys.modules
    assert "acme" not in sys.modules


def test_activate_packages_again_unloads_a_deactivated_package(tmp_path):
    packages_dir = tmp_path / "packages"
    install_package(packages_dir)
    loaded.activate_packages(packages_dir)
    site = str(site_dir(packages_dir, PACKAGE, "1.0.0"))
    manifest = load_manifest(packages_dir)
    manifest.set_active(PACKAGE, None)
    save_manifest(packages_dir, manifest)

    loaded.activate_packages(packages_dir)

    assert site not in sys.path
    assert not loaded.is_loaded(PACKAGE)


def test_activate_packages_again_keeps_an_unchanged_package(tmp_path):
    packages_dir = tmp_path / "packages"
    install_package(packages_dir)
    loaded.activate_packages(packages_dir)
    importlib.import_module("acme.rater.agent")

    loaded.activate_packages(packages_dir)

    site = str(site_dir(packages_dir, PACKAGE, "1.0.0"))
    assert sys.path.count(site) == 1
    assert "acme.rater.agent" in sys.modules


def test_activate_packages_again_forgets_old_failures(tmp_path):
    packages_dir = tmp_path / "packages"
    install_package(packages_dir)
    loaded.mark_failed(PACKAGE, "boom")
    loaded.mark_agent_failed("acme_rater", "boom")

    loaded.activate_packages(packages_dir)

    assert loaded.failures() == {}
    assert loaded.agent_failures() == {}
    assert loaded.is_loaded(PACKAGE)
