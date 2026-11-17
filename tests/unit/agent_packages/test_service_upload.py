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


def test_failure_after_move_cleans_up(tmp_path, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(service, "run_inspection", boom)
    packages = tmp_path / "packages"
    with pytest.raises(RuntimeError):
        _upload(packages, _wheel(tmp_path))
    assert not list((packages / "wheels").glob("*"))
    assert not list((packages / "site").rglob("*"))
    assert _leftovers(packages) == []
