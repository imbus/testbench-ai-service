from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from testbench_ai_service.agent_packages.manifest import (
    ManifestError,
    load_manifest,
    manifest_path,
    save_manifest,
    site_dir,
    wheel_path,
)
from testbench_ai_service.agent_packages.models import InspectionReport, Manifest, PackageVersion


def _version(name: str, version: str, active: bool = False) -> PackageVersion:
    return PackageVersion(
        name=name,
        version=version,
        filename=f"{name}-{version}-py3-none-any.whl",
        sha256="ab" * 32,
        size=10,
        uploaded_at=datetime(2026, 11, 17, tzinfo=timezone.utc),
        uploaded_by=None,
        active=active,
        report=InspectionReport(ok=True),
    )


def test_roundtrip(tmp_path):
    manifest = Manifest(packages={"acme": {"1.0": _version("acme", "1.0", True)}})
    save_manifest(tmp_path / "pkgs", manifest)
    assert manifest_path(tmp_path / "pkgs").is_file()
    assert load_manifest(tmp_path / "pkgs") == manifest


def test_missing_file_gives_empty_manifest(tmp_path):
    assert load_manifest(tmp_path) == Manifest()


def test_broken_json_raises(tmp_path):
    manifest_path(tmp_path).write_text("{nope", encoding="utf-8")
    with pytest.raises(ManifestError):
        load_manifest(tmp_path)


def test_set_active_deactivates_others():
    manifest = Manifest(
        packages={"acme": {"1.0": _version("acme", "1.0", True), "2.0": _version("acme", "2.0")}}
    )
    manifest.set_active("acme", "2.0")
    active = manifest.active("acme")
    assert active is not None
    assert active.version == "2.0"
    assert manifest.packages["acme"]["1.0"].active is False
    manifest.set_active("acme", None)
    assert manifest.active("acme") is None


def test_set_active_unknown_version_raises():
    manifest = Manifest(packages={"acme": {"1.0": _version("acme", "1.0")}})
    with pytest.raises(KeyError):
        manifest.set_active("acme", "9")


def test_site_dir_blocks_escape(tmp_path):
    with pytest.raises(HTTPException) as exc:
        site_dir(tmp_path, "../x", "1.0")
    assert exc.value.status_code == 400
    assert site_dir(tmp_path, "acme", "1.0").name == "1.0"


def test_wheel_path_blocks_escape(tmp_path):
    assert wheel_path(tmp_path, "a.whl").parent.name == "wheels"
    with pytest.raises(HTTPException):
        wheel_path(tmp_path, "../a.whl")
