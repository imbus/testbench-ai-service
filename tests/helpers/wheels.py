"""Build small wheel files for tests."""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import stat
import zipfile
from collections.abc import Sequence
from pathlib import Path


def _record_hash(data: bytes) -> str:
    digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
    return f"sha256={digest}"


def build_wheel(
    tmp_path: Path,
    *,
    name: str = "acme-tb-agents",
    version: str = "1.0.0",
    files: dict[str, str | bytes],
    entry_points: dict[str, str] | None = None,
    requires_dist: Sequence[str] = (),
    tag: str = "py3-none-any",
    corrupt_record: bool = False,
    extra_entries: dict[str, bytes] | None = None,
    symlink: str | None = None,
) -> Path:
    """Write a valid wheel with a correct RECORD (unless ``corrupt_record``)."""
    dist = name.replace("-", "_").replace(".", "_")
    dist_info = f"{dist}-{version}.dist-info"
    metadata = ["Metadata-Version: 2.1", f"Name: {name}", f"Version: {version}"]
    metadata += [f"Requires-Dist: {req}" for req in requires_dist]
    entries: dict[str, bytes] = {}
    for rel, content in files.items():
        entries[rel] = content.encode() if isinstance(content, str) else content
    entries[f"{dist_info}/METADATA"] = ("\n".join(metadata) + "\n").encode()
    entries[f"{dist_info}/WHEEL"] = (
        f"Wheel-Version: 1.0\nGenerator: tests\nRoot-Is-Purelib: true\nTag: {tag}\n"
    ).encode()
    if entry_points:
        lines = ["[testbench_ai_service.agents]"]
        lines += [f"{key} = {value}" for key, value in entry_points.items()]
        entries[f"{dist_info}/entry_points.txt"] = ("\n".join(lines) + "\n").encode()
    entries.update(extra_entries or {})

    record = io.StringIO()
    writer = csv.writer(record, lineterminator="\n")
    for index, (arcname, data) in enumerate(entries.items()):
        digest = _record_hash(data)
        if corrupt_record and index == 0:
            digest = _record_hash(data + b"tampered")
        writer.writerow([arcname, digest, len(data)])
    if symlink:
        writer.writerow([symlink, _record_hash(b"target"), 6])
    writer.writerow([f"{dist_info}/RECORD", "", ""])

    path = tmp_path / f"{dist}-{version}-{tag}.whl"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for arcname, data in entries.items():
            zf.writestr(arcname, data)
        if symlink:
            info = zipfile.ZipInfo(symlink)
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            zf.writestr(info, b"target")
        zf.writestr(f"{dist_info}/RECORD", record.getvalue())
    return path
