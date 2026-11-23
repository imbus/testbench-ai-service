"""Reading and writing the package manifest and locating package files."""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from testbench_ai_service.agent_packages.models import Manifest
from testbench_ai_service.webui.atomic import write_atomic
from testbench_ai_service.webui.security import resolve_within


class ManifestError(Exception):
    """The manifest file exists but cannot be read."""


def manifest_path(packages_dir: Path) -> Path:
    return packages_dir / "manifest.json"


def site_dir(packages_dir: Path, name: str, version: str) -> Path:
    """Directory a package version is unpacked into; refuses paths outside ``site/``."""
    return resolve_within(packages_dir / "site", f"{name}/{version}")


def wheel_path(packages_dir: Path, filename: str) -> Path:
    """Stored location of an uploaded wheel; refuses paths outside ``wheels/``."""
    return resolve_within(packages_dir / "wheels", filename)


def load_manifest(packages_dir: Path) -> Manifest:
    path = manifest_path(packages_dir)
    if not path.is_file():
        return Manifest()
    try:
        return Manifest.model_validate_json(path.read_text(encoding="utf-8"))
    except (ValidationError, ValueError, OSError) as exc:
        raise ManifestError(f"Cannot read {path}: {exc}") from exc


def save_manifest(packages_dir: Path, manifest: Manifest) -> None:
    packages_dir.mkdir(parents=True, exist_ok=True)
    write_atomic(manifest_path(packages_dir), manifest.model_dump_json(indent=2))
