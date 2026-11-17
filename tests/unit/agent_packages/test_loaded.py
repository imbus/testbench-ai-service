from __future__ import annotations

import sys

from testbench_ai_service.agent_packages import loaded
from testbench_ai_service.agent_packages.manifest import manifest_path, site_dir
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
    site = str(site_dir(packages_dir, PACKAGE, "1.0.0"))

    loaded.reset()

    assert site not in sys.path
    assert not loaded.is_loaded(PACKAGE)
    assert loaded.failures() == {}
