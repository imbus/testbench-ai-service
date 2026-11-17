"""Storing and inspecting uploaded agent-package wheels."""

from __future__ import annotations

import contextlib
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import BinaryIO

from testbench_ai_service.agent_packages.manifest import (
    load_manifest,
    save_manifest,
    site_dir,
    wheel_path,
)
from testbench_ai_service.agent_packages.models import PackageVersion
from testbench_ai_service.agent_packages.runner import run_inspection
from testbench_ai_service.agent_packages.wheel import WheelError, extract_wheel, read_wheel

_CHUNK_SIZE = 1024 * 1024


class PackageConflict(Exception):  # noqa: N818
    """The version already exists with different content."""


class PackageInvalid(Exception):  # noqa: N818
    """The upload is not an acceptable wheel."""


def _stream_to_temp(data: BinaryIO, tmp_dir: Path, filename: str, max_bytes: int) -> Path:
    """Copy *data* into a fresh directory under *tmp_dir*; the file keeps the wheel's name."""
    tmp_dir.mkdir(parents=True, exist_ok=True)
    work_dir = Path(tempfile.mkdtemp(dir=tmp_dir))
    path = work_dir / PurePosixPath(filename.replace("\\", "/")).name
    try:
        total = 0
        with path.open("wb") as out:
            while chunk := data.read(_CHUNK_SIZE):
                total += len(chunk)
                if total > max_bytes:
                    raise PackageInvalid(f"larger than {max_bytes // (1024 * 1024)} MB")
                out.write(chunk)
    except BaseException:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise
    return path


def _remove_dir(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)
    with contextlib.suppress(OSError):
        path.parent.rmdir()  # only succeeds when the package has no other version


def store_upload(
    packages_dir: Path,
    filename: str,
    data: BinaryIO,
    max_bytes: int,
    uploaded_by: str | None,
) -> PackageVersion:
    """Store an uploaded wheel, unpack it and inspect it. The version starts inactive.

    Uploading the same version with the same content again returns the existing entry.
    Raises ``PackageInvalid`` for an unusable upload and ``PackageConflict`` when the version
    exists with different content. Callers serialise uploads.
    """
    if not filename.lower().endswith(".whl"):
        raise PackageInvalid("not a wheel (.whl) file")
    temp = _stream_to_temp(data, packages_dir / "tmp", filename, max_bytes)
    try:
        try:
            info = read_wheel(temp)
        except WheelError as exc:
            raise PackageInvalid(str(exc)) from exc

        manifest = load_manifest(packages_dir)
        existing = manifest.packages.get(info.name, {}).get(info.version)
        if existing is not None:
            if existing.sha256 == info.sha256:
                return existing
            raise PackageConflict(
                f"{info.name} {info.version} already exists with different content"
            )

        target_wheel = wheel_path(packages_dir, info.filename)
        target_site = site_dir(packages_dir, info.name, info.version)
        # Not in the manifest, so anything here is a leftover of an interrupted upload.
        target_wheel.unlink(missing_ok=True)
        if target_site.exists():
            shutil.rmtree(target_site)

        target_wheel.parent.mkdir(parents=True, exist_ok=True)
        temp.replace(target_wheel)
        try:
            extract_wheel(target_wheel, target_site)
            report = run_inspection(target_site)
            entry = PackageVersion(
                name=info.name,
                version=info.version,
                filename=info.filename,
                sha256=info.sha256,
                size=info.size,
                uploaded_at=datetime.now(timezone.utc),
                uploaded_by=uploaded_by,
                active=False,
                report=report,
            )
            manifest.packages.setdefault(info.name, {})[info.version] = entry
            save_manifest(packages_dir, manifest)
        except BaseException:
            target_wheel.unlink(missing_ok=True)
            _remove_dir(target_site)
            raise
        return entry
    finally:
        shutil.rmtree(temp.parent, ignore_errors=True)
