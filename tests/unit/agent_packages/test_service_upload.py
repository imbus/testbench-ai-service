from __future__ import annotations

import io
from pathlib import Path

import pytest

from testbench_ai_service.agent_packages import service
from testbench_ai_service.agent_packages.manifest import (
    load_manifest,
    manifest_path,
    site_dir,
    wheel_path,
)
from testbench_ai_service.agent_packages.service import (
    PackageConflict,
    PackageInvalid,
    store_upload,
)
from tests.helpers.wheels import VALID_AGENT_FILES, VALID_ENTRY_POINTS, build_wheel


def _wheel(tmp_path: Path, *, files=None, subdir: str = "src") -> Path:
    src = tmp_path / subdir
    src.mkdir(exist_ok=True)
    return build_wheel(
        src,
        version="1.0.0",
        files=files or VALID_AGENT_FILES,
        entry_points=VALID_ENTRY_POINTS,
    )


def _upload(packages_dir: Path, wheel: Path, max_bytes: int = 10_000_000):
    with wheel.open("rb") as fh:
        return store_upload(packages_dir, wheel.name, fh, max_bytes, "admin")


def _leftovers(packages_dir: Path) -> list[Path]:
    tmp = packages_dir / "tmp"
    return list(tmp.iterdir()) if tmp.exists() else []


def test_valid_upload(tmp_path):
    packages = tmp_path / "packages"
    wheel = _wheel(tmp_path)
    entry = _upload(packages, wheel)
    assert entry.name == "acme-tb-agents"
    assert entry.version == "1.0.0"
    assert entry.active is False
    assert entry.uploaded_by == "admin"
    assert entry.report.ok, entry.report.errors
    assert site_dir(packages, entry.name, entry.version).is_dir()
    assert wheel_path(packages, entry.filename).read_bytes() == wheel.read_bytes()
    assert load_manifest(packages).packages[entry.name][entry.version] == entry
    assert _leftovers(packages) == []


def test_same_upload_twice_is_idempotent(tmp_path):
    packages = tmp_path / "packages"
    wheel = _wheel(tmp_path)
    first = _upload(packages, wheel)
    manifest_before = manifest_path(packages).read_bytes()
    second = _upload(packages, wheel)
    assert second == first
    assert manifest_path(packages).read_bytes() == manifest_before
    assert _leftovers(packages) == []


def _stale_report(packages: Path, entry) -> None:
    """Empty the stored report, as a service version that checked less would have left it."""
    manifest = load_manifest(packages)
    stored = manifest.packages[entry.name][entry.version]
    stored.report = stored.report.model_copy(update={"agents": {}})
    service.save_manifest(packages, manifest)


def test_same_upload_again_replaces_a_stale_report(tmp_path):
    packages = tmp_path / "packages"
    wheel = _wheel(tmp_path)
    first = _upload(packages, wheel)
    _stale_report(packages, first)

    second = _upload(packages, wheel)

    assert second.report == first.report
    assert second.uploaded_at == first.uploaded_at
    assert load_manifest(packages).packages[first.name][first.version] == second


def test_same_upload_again_keeps_a_passing_report_when_the_inspection_fails(tmp_path, monkeypatch):
    packages = tmp_path / "packages"
    wheel = _wheel(tmp_path)
    first = _upload(packages, wheel)
    monkeypatch.setattr(
        service,
        "run_inspection",
        lambda site: first.report.model_copy(update={"ok": False, "errors": ["timed out"]}),
    )

    assert _upload(packages, wheel).report == first.report


def test_same_version_other_content_conflicts(tmp_path):
    packages = tmp_path / "packages"
    first = _upload(packages, _wheel(tmp_path))
    stored = wheel_path(packages, first.filename)
    wheel_before = stored.read_bytes()
    manifest_before = manifest_path(packages).read_bytes()

    changed = {**VALID_AGENT_FILES, "acme/extra.py": "X = 1\n"}
    other = _wheel(tmp_path, files=changed, subdir="other")
    with pytest.raises(PackageConflict):
        _upload(packages, other)

    assert stored.read_bytes() == wheel_before
    assert manifest_path(packages).read_bytes() == manifest_before
    assert not (site_dir(packages, first.name, first.version) / "acme" / "extra.py").exists()
    assert _leftovers(packages) == []


def test_too_large(tmp_path):
    packages = tmp_path / "packages"
    with pytest.raises(PackageInvalid, match="larger than"):
        _upload(packages, _wheel(tmp_path), max_bytes=100)
    assert _leftovers(packages) == []
    assert not manifest_path(packages).exists()


def test_not_a_wheel(tmp_path):
    packages = tmp_path / "packages"
    with pytest.raises(PackageInvalid):
        store_upload(packages, "x.whl", io.BytesIO(b"not a zip"), 1000, None)
    with pytest.raises(PackageInvalid):
        store_upload(packages, "x.txt", io.BytesIO(b"data"), 1000, None)
    assert _leftovers(packages) == []
    assert not manifest_path(packages).exists()


def _stored(packages: Path) -> list[Path]:
    return [*(packages / "wheels").glob("*"), *(packages / "site").rglob("*")]


def test_failure_after_move_cleans_up(tmp_path, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(service, "save_manifest", boom)
    packages = tmp_path / "packages"
    with pytest.raises(RuntimeError):
        _upload(packages, _wheel(tmp_path))
    assert _stored(packages) == []
    assert _leftovers(packages) == []


def test_a_wheel_that_fails_the_inspection_is_not_stored(tmp_path):
    packages = tmp_path / "packages"
    broken = {
        **VALID_AGENT_FILES,
        "acme/rater/agent.py": "raise RuntimeError('broken at import')\n",
    }

    with pytest.raises(PackageInvalid, match=r"was not stored.*broken at import"):
        _upload(packages, _wheel(tmp_path, files=broken))

    assert _stored(packages) == []
    assert _leftovers(packages) == []
    assert not manifest_path(packages).exists()


def test_a_wheel_without_entry_points_is_not_stored(tmp_path):
    packages = tmp_path / "packages"
    src = tmp_path / "src"
    src.mkdir()
    wheel = build_wheel(src, version="1.0.0", files=VALID_AGENT_FILES, entry_points={})

    with pytest.raises(PackageInvalid, match="no entry point"):
        _upload(packages, wheel)

    assert _stored(packages) == []
    assert _leftovers(packages) == []


def test_a_wheel_is_inspected_outside_the_package_storage(tmp_path, monkeypatch):
    packages = tmp_path / "packages"
    inspected: list[Path] = []
    run = service.run_inspection

    def spy(site: Path):
        inspected.append(site)
        assert _stored(packages) == []
        return run(site)

    monkeypatch.setattr(service, "run_inspection", spy)
    _upload(packages, _wheel(tmp_path))

    assert [site.parent.parent for site in inspected] == [packages / "tmp"]


def test_a_rejected_wheel_can_be_uploaded_again_once_fixed(tmp_path):
    packages = tmp_path / "packages"
    broken = {**VALID_AGENT_FILES, "acme/rater/agent.py": "raise RuntimeError('broken')\n"}
    with pytest.raises(PackageInvalid):
        _upload(packages, _wheel(tmp_path, files=broken, subdir="broken"))

    assert _upload(packages, _wheel(tmp_path)).report.ok


def test_a_wheel_with_one_broken_entry_point_is_stored_for_the_others(tmp_path):
    """A finding about one entry point rules out that one, not the package."""
    packages = tmp_path / "packages"
    src = tmp_path / "src"
    src.mkdir()
    wheel = build_wheel(
        src,
        version="1.0.0",
        files={**VALID_AGENT_FILES, "acme/broken.py": "raise RuntimeError('broken at import')\n"},
        entry_points={**VALID_ENTRY_POINTS, "acme_broken": "acme.broken:Missing"},
    )

    entry = _upload(packages, wheel)

    assert entry.report.ok is False
    assert entry.report.agents["acme_rater"].ok is True
    assert entry.report.agents["acme_broken"].ok is False
    assert site_dir(packages, entry.name, entry.version).is_dir()


def test_upload_works_with_a_packages_dir_relative_to_the_working_directory(tmp_path, monkeypatch):
    """The default ``data/agent_packages`` is relative, and the inspection runs elsewhere."""
    wheel = _wheel(tmp_path)
    monkeypatch.chdir(tmp_path)

    entry = _upload(Path("data") / "agent_packages", wheel)

    assert entry.report.ok, entry.report.errors
    assert (tmp_path / "data" / "agent_packages" / "wheels" / entry.filename).is_file()
