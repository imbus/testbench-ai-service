"""Read, validate and unpack agent package wheels.

Wheels come from an admin upload, so every entry is checked before anything is written to disk.
Error messages are meant to be shown to the admin.
"""

from __future__ import annotations

import base64
import configparser
import csv
import hashlib
import io
import re
import shutil
import stat
import zipfile
from dataclasses import dataclass
from email.parser import Parser
from pathlib import Path, PurePosixPath

from packaging.tags import sys_tags
from packaging.utils import InvalidWheelFilename, canonicalize_name, parse_wheel_filename
from packaging.version import InvalidVersion, Version

ENTRY_POINT_GROUP = "testbench_ai_service.agents"
LLM_CLIENT_ENTRY_POINT_GROUP = "testbench_ai_service.llm_clients"
MAX_UNPACKED_BYTES = 200 * 1024 * 1024
MAX_FILES = 5000
_CHUNK = 1024 * 1024
_RECORD_COLUMNS = 3
_NAME_RE = re.compile(r"^([A-Z0-9]|[A-Z0-9][A-Z0-9._-]*[A-Z0-9])$", re.IGNORECASE)
_SIGNATURE_FILES = {"RECORD.jws", "RECORD.p7s"}


class WheelError(ValueError):
    """The wheel is invalid or unsafe. The message is readable for admins."""


@dataclass(frozen=True)
class WheelInfo:
    name: str
    version: str
    filename: str
    sha256: str
    size: int
    requires_dist: list[str]
    entry_points: dict[str, str]
    top_level_modules: list[str]


def _check_path(name: str) -> None:
    normalized = name.replace("\\", "/")
    if normalized.startswith("/") or any(
        part == ".." or ":" in part for part in normalized.split("/")
    ):
        raise WheelError(f"The wheel contains an unsafe path: {name!r}.")


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    return stat.S_ISLNK(info.external_attr >> 16)


def _hash_member(zf: zipfile.ZipFile, info: zipfile.ZipInfo, algorithm: str) -> tuple[str, int]:
    hasher = hashlib.new(algorithm)
    total = 0
    with zf.open(info) as handle:
        while chunk := handle.read(_CHUNK):
            total += len(chunk)
            if total > MAX_UNPACKED_BYTES:
                raise WheelError("The unpacked wheel is too large.")
            hasher.update(chunk)
    return base64.urlsafe_b64encode(hasher.digest()).rstrip(b"=").decode(), total


def _read_text(zf: zipfile.ZipFile, name: str) -> str:
    try:
        return zf.read(name).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise WheelError(f"{name} is not valid UTF-8.") from exc


def _check_all_listed(
    members: dict[str, zipfile.ZipInfo], listed: set[str], record_name: str
) -> None:
    for path in members:
        if (
            path != record_name
            and path not in listed
            and path.rsplit("/", 1)[-1] not in _SIGNATURE_FILES
        ):
            raise WheelError(f"{path!r} is in the wheel but not in the RECORD file.")


def _verify_record(
    zf: zipfile.ZipFile, dist_info: str, members: dict[str, zipfile.ZipInfo]
) -> None:
    record_name = f"{dist_info}/RECORD"
    listed: set[str] = set()
    for row in csv.reader(io.StringIO(_read_text(zf, record_name))):
        if not row:
            continue
        if len(row) != _RECORD_COLUMNS:
            raise WheelError("The RECORD file is malformed.")
        path, hash_spec, _size = row
        listed.add(path)
        if path == record_name or path.rsplit("/", 1)[-1] in _SIGNATURE_FILES:
            continue
        if not hash_spec:
            raise WheelError(f"The RECORD file has no hash for {path!r}.")
        member = members.get(path)
        if member is None:
            raise WheelError(f"The RECORD file lists {path!r}, which is not in the wheel.")
        algorithm, _, expected = hash_spec.partition("=")
        if algorithm not in ("sha256", "sha384", "sha512"):
            raise WheelError(f"The RECORD file uses an unsupported hash for {path!r}.")
        actual, _total = _hash_member(zf, member, algorithm)
        if actual != expected.rstrip("="):
            raise WheelError(f"The RECORD hash of {path!r} does not match its content.")
    _check_all_listed(members, listed, record_name)


def _top_level_modules(
    zf: zipfile.ZipFile, dist_info: str, members: dict[str, zipfile.ZipInfo]
) -> list[str]:
    top_level_name = f"{dist_info}/top_level.txt"
    if top_level_name in members:
        names = [line.strip() for line in _read_text(zf, top_level_name).splitlines()]
        return sorted({n for n in names if n})
    found: set[str] = set()
    for path in members:
        first = PurePosixPath(path).parts[0]
        if first.endswith((".dist-info", ".data")):
            continue
        found.add(first[:-3] if first.endswith(".py") and "/" not in path else first)
    return sorted(found)


def _entry_points(
    zf: zipfile.ZipFile, dist_info: str, members: dict[str, zipfile.ZipInfo]
) -> dict[str, str]:
    name = f"{dist_info}/entry_points.txt"
    if name not in members:
        return {}
    parser = configparser.ConfigParser(delimiters=("=",), interpolation=None)
    parser.optionxform = str  # type: ignore[assignment,method-assign]
    try:
        parser.read_string(_read_text(zf, name))
    except configparser.Error as exc:
        raise WheelError(f"The entry_points.txt file is malformed: {exc}") from exc
    if not parser.has_section(ENTRY_POINT_GROUP):
        return {}
    return {key: value.strip() for key, value in parser.items(ENTRY_POINT_GROUP)}


def _check_compatible(filename: str) -> tuple[str, str]:
    """Validate the file name and tags. Returns the normalized name and version."""
    try:
        name, version, _build, tags = parse_wheel_filename(filename)
    except InvalidWheelFilename as exc:
        raise WheelError(f"{filename!r} is not a valid wheel file name.") from exc
    if not tags & set(sys_tags()):
        raise WheelError(
            f"The wheel {filename!r} is not compatible with this service's Python "
            "version or platform."
        )
    return str(name), str(version)


def _collect_members(zf: zipfile.ZipFile) -> dict[str, zipfile.ZipInfo]:
    if len(zf.infolist()) > MAX_FILES:
        raise WheelError(f"The wheel contains more than {MAX_FILES} files.")
    members: dict[str, zipfile.ZipInfo] = {}
    total = 0
    for info in zf.infolist():
        _check_path(info.filename)
        if info.is_dir():
            continue
        if _is_symlink(info):
            raise WheelError(f"The wheel contains a symlink: {info.filename!r}.")
        total += info.file_size
        members[info.filename] = info
    if total > MAX_UNPACKED_BYTES:
        raise WheelError("The unpacked wheel would be too large.")
    return members


def _validate_identity(
    name: str | None, version: str | None, file_name: str, file_version: str
) -> tuple[str, str]:
    if not name or not version:
        raise WheelError("The wheel METADATA has no Name or Version.")
    if not _NAME_RE.fullmatch(name):
        raise WheelError(f"The wheel METADATA has an invalid name: {name!r}.")
    try:
        parsed = str(Version(version))
    except InvalidVersion as exc:
        raise WheelError(f"The wheel METADATA has an invalid version: {version!r}.") from exc
    normalized = str(canonicalize_name(name))
    if normalized != file_name or parsed != file_version:
        raise WheelError(
            "The wheel METADATA does not match its file name "
            f"({normalized} {parsed} vs. {file_name} {file_version})."
        )
    return normalized, parsed


def read_wheel(path: Path) -> WheelInfo:
    """Validate a wheel and return its metadata. Raises ``WheelError``."""
    file_name, file_version = _check_compatible(path.name)

    try:
        zf = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as exc:
        raise WheelError("The file is not a valid wheel (ZIP archive).") from exc
    with zf:
        members = _collect_members(zf)

        dist_infos = {
            p.split("/", 1)[0] for p in members if p.split("/", 1)[0].endswith(".dist-info")
        }
        if len(dist_infos) != 1:
            raise WheelError("The wheel must contain exactly one .dist-info directory.")
        dist_info = dist_infos.pop()
        for required in ("METADATA", "WHEEL", "RECORD"):
            if f"{dist_info}/{required}" not in members:
                raise WheelError(f"The wheel has no {required} file.")

        _verify_record(zf, dist_info, members)
        metadata = Parser().parsestr(_read_text(zf, f"{dist_info}/METADATA"))
        name, version = metadata.get("Name"), metadata.get("Version")
        name, version = _validate_identity(name, version, file_name, file_version)
        return WheelInfo(
            name=name,
            version=version,
            filename=path.name,
            sha256=_file_sha256(path),
            size=path.stat().st_size,
            requires_dist=[str(r) for r in (metadata.get_all("Requires-Dist") or [])],
            entry_points=_entry_points(zf, dist_info, members),
            top_level_modules=_top_level_modules(zf, dist_info, members),
        )


def _file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK):
            hasher.update(chunk)
    return hasher.hexdigest()


def extract_wheel(path: Path, target: Path) -> None:
    """Unpack a validated wheel into ``target`` atomically (via ``<target>.tmp``)."""
    if target.exists():
        raise WheelError(f"The target directory {target.name!r} already exists.")
    tmp = target.with_name(target.name + ".tmp")
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    root = tmp.resolve()
    try:
        with zipfile.ZipFile(path) as zf:
            for info in zf.infolist():
                _check_path(info.filename)
                if _is_symlink(info):
                    raise WheelError(f"The wheel contains a symlink: {info.filename!r}.")
                dest = (root / info.filename).resolve()
                if root != dest and root not in dest.parents:
                    raise WheelError(f"The wheel contains an unsafe path: {info.filename!r}.")
                if info.is_dir():
                    dest.mkdir(parents=True, exist_ok=True)
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, dest.open("wb") as out:
                    shutil.copyfileobj(src, out)
        tmp.replace(target)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
