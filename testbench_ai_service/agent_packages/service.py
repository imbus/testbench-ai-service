"""Storing uploaded agent-package wheels and configuring the agents they provide."""

from __future__ import annotations

import contextlib
import re
import shutil
import tempfile
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO

from pydantic import BaseModel, Field

from testbench_ai_service.agent_packages import loaded
from testbench_ai_service.agent_packages.manifest import (
    load_manifest,
    save_manifest,
    site_dir,
    wheel_path,
)
from testbench_ai_service.agent_packages.models import (
    AgentReport,
    InspectionReport,
    LLMClientReport,
    Manifest,
    PackageVersion,
)
from testbench_ai_service.agent_packages.runner import run_inspection
from testbench_ai_service.agent_packages.wheel import WheelError, extract_wheel, read_wheel
from testbench_ai_service.config import DEFAULT_AGENTS, PROMPTS_DIR, TEMPLATES_DIR, AppConfig
from testbench_ai_service.log import logger
from testbench_ai_service.validators import validate_endpoint_path
from testbench_ai_service.webui.atomic import write_atomic
from testbench_ai_service.webui.config_io import read_config_file
from testbench_ai_service.webui.models import ConfigIssue
from testbench_ai_service.webui.multi_write import MultiWriteResult, write_all
from testbench_ai_service.webui.paths import join_path
from testbench_ai_service.webui.plan import plan_change
from testbench_ai_service.webui.security import resolve_within

_CHUNK_SIZE = 1024 * 1024


class PackageConflict(Exception):  # noqa: N818
    """The version already exists with different content, or a name is already taken."""


class PackageInvalid(Exception):  # noqa: N818
    """The upload is not an acceptable wheel, or its agents cannot be configured."""

    def __init__(self, message: str, issues: list[ConfigIssue] | None = None) -> None:
        super().__init__(message)
        self.issues = issues or []


class PackageTooLarge(PackageInvalid):
    """The upload exceeds the size limit."""


class PackageNotFound(LookupError):  # noqa: N818
    """The package or version is not in the manifest."""


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
                    raise PackageTooLarge(f"larger than {max_bytes // (1024 * 1024)} MB")
                out.write(chunk)
    except BaseException:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise
    return path


def _remove_dir(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)
    with contextlib.suppress(OSError):
        path.parent.rmdir()  # only succeeds when the package has no other version


def _refresh_report(
    packages_dir: Path, manifest: Manifest, entry: PackageVersion
) -> PackageVersion:
    """Inspect a stored version again and keep the new report.

    A report is as old as its upload: one written by a service version that did not
    check LLM clients yet lists none, and uploading the wheel again would only hand
    that report back. A passing report is not replaced by a failing one, so an
    inspection that times out leaves a version in use alone.
    """
    target_site = site_dir(packages_dir, entry.name, entry.version)
    if not target_site.is_dir():
        return entry
    report = run_inspection(target_site)
    if report != entry.report and (report.ok or not entry.report.ok):
        entry.report = report
        save_manifest(packages_dir, manifest)
    return entry


def store_upload(
    packages_dir: Path,
    filename: str,
    data: BinaryIO,
    max_bytes: int,
    uploaded_by: str | None,
) -> PackageVersion:
    """Inspect an uploaded wheel and store it if it passes. The version starts inactive.

    The wheel is unpacked and inspected in a throw-away directory under ``tmp``; only a
    wheel with something usable in it reaches the package storage (see ``_usable``). A
    wheel that fails as a whole can be used by nothing, so it is refused with the reasons
    and leaves nothing behind. One whose check fails for single entry points only is
    stored: its report says which, and the others can be registered.

    Uploading the same version with the same content again returns the existing entry,
    inspected anew.
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
                return _refresh_report(packages_dir, manifest, existing)
            raise PackageConflict(
                f"{info.name} {info.version} already exists with different content"
            )

        try:
            extract_wheel(temp, temp.parent / "site")
        except WheelError as exc:
            raise PackageInvalid(str(exc)) from exc
        report = run_inspection(temp.parent / "site")
        if not _usable(report):
            raise PackageInvalid(
                f"{info.name} {info.version} failed the inspection and was not stored: "
                + "; ".join(_report_errors(report))
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
            # Unpacked anew: the inspected copy holds the bytecode its imports left behind.
            extract_wheel(target_wheel, target_site)
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


def _report_errors(report: InspectionReport) -> list[str]:
    """Every reason a report failed: the package's own, then each entry point's."""
    errors = list(report.errors)
    for name, item in [*report.agents.items(), *report.llm_clients.items()]:
        errors += [f"{name}: {error}" for error in item.errors]
    return errors or ["no details"]


# --- Configuring the agents of a package ------------------------------------------------

_LANGUAGES = ("en", "de")
_RESTART_PACKAGES = "agent_packages"


class RegisterAgent(BaseModel):
    """One entry point of a package to configure as an agent."""

    entry_point: str
    agent_key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    endpoint_path: str = Field(pattern=r"^/[a-z0-9][a-z0-9/_-]{0,127}$")
    enabled: bool = True


class FileConflict(BaseModel):
    """A prompt or template file that exists with other content than the package's."""

    path: str  # relative to prompts_dir/templates_dir, prefixed "prompts/" or "templates/"
    current: str
    incoming: str


class FileConflicts(Exception):  # noqa: N818
    """Copying the package's files would overwrite files not listed in ``overwrite``."""

    def __init__(self, conflicts: list[FileConflict]) -> None:
        super().__init__(", ".join(conflict.path for conflict in conflicts))
        self.conflicts = conflicts


class DefaultDirs(Exception):  # noqa: N818
    """The shipped prompt or template directory is in use; package files cannot go there."""


class RegisterResult(BaseModel):
    written: list[str]
    backup: str | None
    restart_required: list[str]


def uses_default_dirs(config: AppConfig) -> bool:
    """Whether the shipped prompt or template directory is in use (or none is set)."""
    return (
        config.prompts_dir is None
        or config.templates_dir is None
        or config.prompts_dir.resolve() == PROMPTS_DIR
        or config.templates_dir.resolve() == TEMPLATES_DIR
    )


def _custom_dirs(config: AppConfig) -> tuple[Path, Path]:
    prompts_dir, templates_dir = config.prompts_dir, config.templates_dir
    if prompts_dir is None or templates_dir is None or uses_default_dirs(config):
        raise DefaultDirs(
            "set prompts_dir and templates_dir to your own directories before configuring "
            "agents from a package"
        )
    return prompts_dir, templates_dir


def _version(manifest: Manifest, name: str, version: str) -> PackageVersion:
    entry = manifest.packages.get(name, {}).get(version)
    if entry is None:
        raise PackageNotFound(f"{name} {version} is not uploaded")
    return entry


def _usable(report: InspectionReport) -> bool:
    """Whether anything of the package can be used.

    A finding about the package as a whole (a clashing module, an unmet
    requirement, a timeout) rules out all of it. A finding about one entry
    point rules out that entry point only: the others are registered and used
    on their own, and each such use checks its own entry point.
    """
    entries = [*report.agents.values(), *report.llm_clients.values()]
    return not report.errors and any(entry.ok for entry in entries)


def _require_ok(entry: PackageVersion) -> None:
    if not _usable(entry.report):
        raise PackageInvalid(
            f"{entry.name} {entry.version} failed the inspection: "
            + "; ".join(_report_errors(entry.report))
        )


def _disk_agents(section: dict[str, Any]) -> dict[str, dict[str, Any]]:
    agents = section.get("agents") or {}
    return {key: agent for key, agent in agents.items() if isinstance(agent, dict)}


def _package_agents(
    section: dict[str, Any], name: str, running: AppConfig | None = None
) -> dict[str, str]:
    """Agent key to ``class_path`` of every agent configured from package *name*.

    *section* is the config file on disk, the source of truth: an agent registered or
    removed since the start is not reflected in the running config until the restart.
    With *running*, its agents of *name* are included too (only for removing, where an
    extra key is harmless).
    """
    agents: dict[str, str] = {}
    if running is not None:
        agents = {
            key: agent.class_path for key, agent in running.agents.items() if agent.package == name
        }
    for key, agent in _disk_agents(section).items():
        if agent.get("package") == name:
            agents[key] = str(agent.get("class_path", ""))
    return agents


def _module_dir(site: Path, class_path: str) -> Path:
    """Directory of the module that defines *class_path* inside an unpacked package."""
    module = class_path.rsplit(".", 1)[0]
    module_path = resolve_within(site, module.replace(".", "/"))
    if module_path.is_dir():  # the module is a package: its __init__.py lives in there
        return module_path
    return module_path.parent


def _package_files(
    site: Path, class_path: str, agent_key: str, prompts_dir: Path, templates_dir: Path
) -> dict[Path, tuple[str, bytes]]:
    """Target path to (conflict label, content) of the prompts and templates of one agent."""
    module_dir = _module_dir(site, class_path)
    files: dict[Path, tuple[str, bytes]] = {}
    for kind, base in (("prompts", prompts_dir), ("templates", templates_dir)):
        for lang in _LANGUAGES:
            source = module_dir / kind / lang
            if not source.is_dir():
                continue
            target_dir = resolve_within(base, f"{lang}/{agent_key}")
            for file in sorted(source.rglob("*")):
                if file.is_symlink() or not file.is_file():
                    continue
                rel = file.relative_to(source).as_posix()
                target = resolve_within(target_dir, rel)
                files[target] = (f"{kind}/{lang}/{agent_key}/{rel}", file.read_bytes())
    return files


def _decode(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")


def _files_to_write(
    files: dict[Path, tuple[str, bytes]], overwrite: Iterable[str], keep: Iterable[str] = ()
) -> dict[Path, str | bytes]:
    """Drop files already present with the same content or listed in *keep*; refuse
    differing files listed in neither *keep* nor *overwrite*.

    Raises:
        PackageInvalid: A file is listed in both *keep* and *overwrite*.
        FileConflicts: Every differing file that is in neither list.
    """
    allowed = set(overwrite)
    kept = set(keep)
    both = sorted(allowed & kept)
    if both:
        raise PackageInvalid(f"files both kept and overwritten: {', '.join(both)}")
    to_write: dict[Path, str | bytes] = {}
    conflicts: list[FileConflict] = []
    for target, (label, content) in files.items():
        if target.is_file():
            current = target.read_bytes()
            if current == content or label in kept:
                continue
            if label not in allowed:
                conflicts.append(
                    FileConflict(path=label, current=_decode(current), incoming=_decode(content))
                )
                continue
        to_write[target] = content
    if conflicts:
        raise FileConflicts(sorted(conflicts, key=lambda conflict: conflict.path))
    return to_write


def _make_dirs(targets: Iterable[Path], created: list[Path]) -> None:
    """Create the parent directories of *targets*, appending each to *created*
    (outermost first) as soon as it exists, so a partial failure can be undone."""
    for target in targets:
        missing: list[Path] = []
        parent = target.parent
        while not parent.exists():
            missing.append(parent)
            parent = parent.parent
        for directory in reversed(missing):
            directory.mkdir()
            created.append(directory)


def _backup_path(path: Path) -> Path:
    return path.with_name(f"{path.name}.bak")  # the name write_all backs up to


def _old_backups(targets: Iterable[Path]) -> dict[Path, bytes | None]:
    """``.bak`` path to its current content (``None``: absent) for every existing target,
    i.e. every backup ``write_all`` is about to create or overwrite."""
    backups: dict[Path, bytes | None] = {}
    for target in targets:
        if target.is_file():
            backup = _backup_path(target)
            backups[backup] = backup.read_bytes() if backup.is_file() else None
    return backups


def _undo_files(
    result: MultiWriteResult | None,
    created_dirs: list[Path],
    old_backups: dict[Path, bytes | None],
) -> None:
    """Restore what a completed ``write_all`` replaced, remove what it created and put
    the ``.bak`` files back as they were before."""
    if result is not None:
        for path in result.written:
            backup = result.backups.get(path)
            try:
                if backup is None:
                    path.unlink(missing_ok=True)
                else:
                    path.write_bytes(backup.read_bytes())
            except OSError as e:  # pragma: no cover - best effort, already failing
                logger.error("Could not roll %s back: %s", path, e)
    for backup, content in old_backups.items():
        try:
            if content is None:
                backup.unlink(missing_ok=True)
            else:
                backup.write_bytes(content)
        except OSError as e:  # pragma: no cover - best effort, already failing
            logger.error("Could not restore %s: %s", backup, e)
    for directory in reversed(created_dirs):
        with contextlib.suppress(OSError):
            directory.rmdir()


def _apply(
    config: AppConfig,
    config_path: Path,
    old_manifest: Manifest,
    new_manifest: Manifest,
    files: dict[Path, str | bytes],
    edits: dict[str, Any],
) -> RegisterResult:
    """Write *files*, the config *edits* and *new_manifest*, or none of them.

    Config validation checks the prompt files on disk, and it describes a package
    agent that is not loaded by the report of the package's *active* version
    (``agent_info``). So the new manifest and the files are written first, then the
    edits are validated and written. Any failure restores the files and the previous
    manifest before the exception passes on.
    """
    packages_dir = config.agent_packages.dir
    save_manifest(packages_dir, new_manifest)
    result: MultiWriteResult | None = None
    created_dirs: list[Path] = []
    old_backups = _old_backups(files)
    try:
        _make_dirs(files, created_dirs)
        result = write_all(files)
        preview, text, has_write = plan_change(edits, config_path, config, allow_server_only=True)
        if not preview.valid:
            reasons = "; ".join(
                f"{issue.path}: {issue.message}" if issue.path else issue.message
                for issue in preview.issues
            )
            raise PackageInvalid(
                f"the configuration would not be valid: {reasons}", issues=preview.issues
            )
        backup = write_atomic(config_path, text) if has_write else None
    except BaseException:
        _undo_files(result, created_dirs, old_backups)
        save_manifest(packages_dir, old_manifest)
        raise
    written = [str(path) for path in result.written]
    if has_write:
        written.append(str(config_path.resolve()))
    return RegisterResult(
        written=written,
        backup=str(backup) if backup is not None else None,
        restart_required=list(preview.restart_required),
    )


def _with_packages_restart(result: RegisterResult) -> RegisterResult:
    result.restart_required = sorted({*result.restart_required, _RESTART_PACKAGES})
    return result


def _agent_edits(item: RegisterAgent, report: AgentReport, package: str) -> dict[str, Any]:
    def path(*segments: str) -> str:
        return join_path(["agents", item.agent_key, *segments])

    edits: dict[str, Any] = {
        path("enabled"): item.enabled,
        path("endpoint_path"): item.endpoint_path,
        path("class_path"): report.class_path,
        path("prompt", "file"): f"{item.agent_key}/prompt.yaml",
        path("package"): package,
    }
    properties = (report.args_schema or {}).get("properties") or {}
    defaults = {
        key: spec["default"]
        for key, spec in properties.items()
        if isinstance(spec, dict) and "default" in spec
    }
    if defaults:
        edits[path("args")] = defaults
    return edits


def register_agents(
    config: AppConfig,
    config_path: Path,
    name: str,
    version: str,
    agents: list[RegisterAgent],
    overwrite: list[str],
    keep: list[str] | None = None,
) -> RegisterResult:
    """Configure entry points of *name* *version* as agents and make the version active.

    Copies each agent's prompts and templates into ``prompts_dir``/``templates_dir``
    under ``<lang>/<agent_key>/`` and adds ``agents.<agent_key>`` to the config.
    Callers serialise package operations.

    Raises:
        DefaultDirs: The shipped prompt or template directory is in use.
        PackageNotFound: The version is not uploaded.
        PackageInvalid: The version or a chosen entry point failed the inspection, or
            the resulting config would not be valid.
        PackageConflict: An agent key or endpoint path is taken, or another version
            of the package is active (switch with ``activate_version`` first).
        FileConflicts: Files differ that are listed in neither *overwrite* nor *keep*.
            Files in *keep* are left as they are.
    """
    prompts_dir, templates_dir = _custom_dirs(config)
    packages_dir = config.agent_packages.dir
    manifest = load_manifest(packages_dir)
    entry = _version(manifest, name, version)
    _require_ok(entry)
    active = manifest.active(name)
    if active is not None and active.version != version:
        raise PackageConflict(
            f"{name} {active.version} is active; switch to {version} before registering "
            "agents from it"
        )

    disk_agents = _disk_agents(read_config_file(config_path))
    taken_keys = set(config.agents) | set(DEFAULT_AGENTS) | set(disk_agents)
    taken_paths = {agent.endpoint_path for agent in config.agents.values()} | {
        agent.get("endpoint_path") for agent in disk_agents.values()
    }
    reports: dict[str, AgentReport] = {}
    for item in agents:
        report = entry.report.agents.get(item.entry_point)
        if report is None or not report.ok:
            raise PackageInvalid(f"entry point '{item.entry_point}' is not a usable agent")
        if item.agent_key in taken_keys:
            raise PackageConflict(f"agent '{item.agent_key}' already exists")
        try:
            validate_endpoint_path(item.endpoint_path)
        except ValueError as exc:
            raise PackageConflict(str(exc)) from exc
        if item.endpoint_path in taken_paths:
            raise PackageConflict(f"endpoint '{item.endpoint_path}' is already in use")
        taken_keys.add(item.agent_key)
        taken_paths.add(item.endpoint_path)
        reports[item.agent_key] = report

    site = site_dir(packages_dir, name, version)
    files: dict[Path, tuple[str, bytes]] = {}
    edits: dict[str, Any] = {}
    for item in agents:
        report = reports[item.agent_key]
        files.update(
            _package_files(site, report.class_path, item.agent_key, prompts_dir, templates_dir)
        )
        edits.update(_agent_edits(item, report, name))
    to_write = _files_to_write(files, overwrite, keep or [])

    new_manifest = manifest.model_copy(deep=True)
    new_manifest.set_active(name, version)
    result = _apply(config, config_path, manifest, new_manifest, to_write, edits)
    return _with_packages_restart(result) if active is None else result


def _matching_report(
    entry: PackageVersion, current: PackageVersion | None, class_path: str
) -> AgentReport | None:
    """The report of *entry* for the agent configured with *class_path*.

    Found through the entry point that provides *class_path* in the *current* version,
    so a class moved to another module is followed; otherwise by *class_path* itself.
    """
    if current is not None:
        for entry_point, report in current.report.agents.items():
            if report.class_path == class_path and entry_point in entry.report.agents:
                return entry.report.agents[entry_point]
    for report in entry.report.agents.values():
        if report.class_path == class_path:
            return report
    return None


def activate_version(
    config: AppConfig,
    config_path: Path,
    name: str,
    version: str,
    overwrite: list[str],
    keep: list[str] | None = None,
) -> RegisterResult:
    """Make *version* the active version of *name*; it is loaded at the next start.

    Every agent configured from the package must have an ``ok`` agent in *version*,
    otherwise the next start would fail. A moved ``class_path`` is updated in the
    config, and the agents' prompts and templates are copied as in ``register_agents``.

    Raises:
        DefaultDirs, PackageNotFound, PackageInvalid, FileConflicts: As in
            ``register_agents``.
    """
    section = read_config_file(config_path)
    configured = _package_agents(section, name)
    client_path = package_llm_client(section, name)
    # Only agents bring prompt and template files; an LLM client needs no directories.
    dirs = _custom_dirs(config) if configured else None
    packages_dir = config.agent_packages.dir
    manifest = load_manifest(packages_dir)
    entry = _version(manifest, name, version)
    _require_ok(entry)
    current = manifest.active(name)

    site = site_dir(packages_dir, name, version)
    files: dict[Path, tuple[str, bytes]] = {}
    edits: dict[str, Any] = {}
    for key, class_path in sorted(configured.items()):
        report = _matching_report(entry, current, class_path)
        if report is None or not report.ok:
            raise PackageInvalid(f"{name} {version} has no usable agent for '{key}' ({class_path})")
        if report.class_path != class_path:
            edits[join_path(["agents", key, "class_path"])] = report.class_path
        assert dirs is not None  # set whenever the package has configured agents
        files.update(_package_files(site, report.class_path, key, *dirs))
    if client_path is not None:
        client = _matching_llm_report(entry, current, client_path)
        if client is None or not client.ok:
            raise PackageInvalid(
                f"{name} {version} has no usable LLM client for '{client_path}', which the "
                "service uses"
            )
        if client.class_path != client_path:
            edits[join_path(["llm_config", "class_path"])] = client.class_path
    to_write = _files_to_write(files, overwrite, keep or [])

    new_manifest = manifest.model_copy(deep=True)
    new_manifest.set_active(name, version)
    result = _apply(config, config_path, manifest, new_manifest, to_write, edits)
    return _with_packages_restart(result)


def remove_package(config: AppConfig, config_path: Path, name: str) -> RegisterResult:
    """Remove every agent of *name* and their project overrides from the config.

    The package is deactivated. Prompt and template files and the uploaded versions
    stay; versions are deleted with ``delete_version``.

    Raises:
        PackageNotFound: Neither the manifest nor the config knows *name*.
        PackageInvalid: The config without the agents would not be valid.
        PackageConflict: The package provides the LLM client in use
            (``clear_llm_client`` first).
    """
    manifest = load_manifest(config.agent_packages.dir)
    section = read_config_file(config_path)
    if package_llm_client(section, name) is not None:
        raise PackageConflict(f"{name} provides the LLM client; stop using it first")
    keys = sorted(_package_agents(section, name, running=config))
    if name not in manifest.packages and not keys:
        raise PackageNotFound(f"{name} is not uploaded")

    overrides: dict[str, set[str]] = {
        project: set(table.agents or {}) for project, table in config.projects.items()
    }
    for project, table in (section.get("projects") or {}).items():
        if isinstance(table, dict) and isinstance(table.get("agents"), dict):
            overrides.setdefault(project, set()).update(table["agents"])
    edits: dict[str, Any] = {join_path(["agents", key]): None for key in keys}
    for project, agent_keys in sorted(overrides.items()):
        for key in keys:
            if key in agent_keys:
                edits[join_path(["projects", project, "agents", key])] = None

    was_active = manifest.active(name) is not None
    new_manifest = manifest.model_copy(deep=True)
    if name in new_manifest.packages:
        new_manifest.set_active(name, None)
    result = _apply(config, config_path, manifest, new_manifest, {}, edits)
    return _with_packages_restart(result) if was_active else result


# --- The LLM client of a package --------------------------------------------------------

_CUSTOM = "custom"
_MODEL_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,127}$")
#: Model names the client factory routes to OpenAI or Anthropic whatever the provider is.
_ROUTED_ELSEWHERE = re.compile(r"^(gpt-|claude-|o\d+)")


def _llm_section(section: dict[str, Any]) -> dict[str, Any]:
    llm = section.get("llm_config")
    return llm if isinstance(llm, dict) else {}


def package_llm_client(section: dict[str, Any], name: str) -> str | None:
    """The ``class_path`` of the LLM client the config file takes from package *name*.

    *section* is the config file on disk. ``None`` unless its ``llm_config`` uses the
    custom provider with ``package = name``.
    """
    llm = _llm_section(section)
    if llm.get("provider") != _CUSTOM or llm.get("package") != name:
        return None
    return str(llm.get("class_path", ""))


def _custom_models(section: dict[str, Any]) -> list[str]:
    """The ``extra_models`` of the config file that belong to the custom provider."""
    models = _llm_section(section).get("extra_models")
    if not isinstance(models, dict):
        return []
    return [
        model
        for model, entry in models.items()
        if isinstance(entry, dict) and entry.get("provider") == _CUSTOM
    ]


def _matching_llm_report(
    entry: PackageVersion, current: PackageVersion | None, class_path: str
) -> LLMClientReport | None:
    """The report of *entry* for the LLM client configured with *class_path*; a class
    moved to another module is followed through its entry point, as for agents."""
    if current is not None:
        for entry_point, report in current.report.llm_clients.items():
            if report.class_path == class_path and entry_point in entry.report.llm_clients:
                return entry.report.llm_clients[entry_point]
    for report in entry.report.llm_clients.values():
        if report.class_path == class_path:
            return report
    return None


def _check_models(models: list[str], default_model: str | None) -> None:
    from testbench_ai_service.llm.routing import builtin_routing  # noqa: PLC0415

    if not models:
        raise PackageInvalid("name at least one model the LLM client serves")
    if len(set(models)) != len(models):
        raise PackageInvalid("a model is listed twice")
    for model in models:
        if not _MODEL_NAME.match(model):
            raise PackageInvalid(f"'{model}' is not a valid model name")
        if _ROUTED_ELSEWHERE.match(model) or builtin_routing(model) is not None:
            raise PackageInvalid(
                f"'{model}' would never reach the client: names starting with 'gpt-', "
                "'claude-' or 'o<digit>' always go to OpenAI or Anthropic"
            )
    if default_model is not None and default_model not in models:
        raise PackageInvalid(f"the default model '{default_model}' is not one of the models")


def use_llm_client(
    config: AppConfig,
    config_path: Path,
    name: str,
    version: str,
    entry_point: str,
    models: list[str],
    default_model: str | None = None,
) -> RegisterResult:
    """Make an LLM client of *name* *version* the service's custom provider.

    Sets ``llm_config.provider``, ``class_path`` and ``package``, lists *models* as the
    custom provider's ``extra_models`` (replacing its previous ones) and makes the
    version active. With *default_model*, ``llm_config.model`` is set to it. The client
    is loaded at the next start. Callers serialise package operations.

    Raises:
        PackageNotFound: The version is not uploaded.
        PackageInvalid: The version or the entry point failed the inspection, a model
            name is unusable, or the resulting config would not be valid.
        PackageConflict: Another version of the package is active.
    """
    packages_dir = config.agent_packages.dir
    manifest = load_manifest(packages_dir)
    entry = _version(manifest, name, version)
    _require_ok(entry)
    active = manifest.active(name)
    if active is not None and active.version != version:
        raise PackageConflict(
            f"{name} {active.version} is active; switch to {version} before using its LLM client"
        )
    report = entry.report.llm_clients.get(entry_point)
    if report is None or not report.ok:
        raise PackageInvalid(f"entry point '{entry_point}' is not a usable LLM client")
    _check_models(models, default_model)

    def path(*segments: str) -> str:
        return join_path(["llm_config", *segments])

    edits: dict[str, Any] = {
        path("provider"): _CUSTOM,
        path("class_path"): report.class_path,
        path("package"): name,
    }
    for stale in _custom_models(read_config_file(config_path)):
        if stale not in models:
            edits[path("extra_models", stale)] = None
    for model in models:
        edits[path("extra_models", model)] = {"provider": _CUSTOM, "routing": "fallback"}
    if default_model is not None:
        edits[path("model")] = default_model

    new_manifest = manifest.model_copy(deep=True)
    new_manifest.set_active(name, version)
    return _with_packages_restart(_apply(config, config_path, manifest, new_manifest, {}, edits))


def _remove_keys(edits: dict[str, Any], table: list[str], present: Any, remove: set[str]) -> None:
    """Add edits that drop *remove* from the config table at *table*; the table itself
    goes when nothing else is left in it."""
    if not isinstance(present, dict) or not remove & set(present):
        return
    if set(present) <= remove:
        edits[join_path(table)] = None
        return
    for key in sorted(remove & set(present)):
        edits[join_path([*table, key])] = None


def clear_llm_client(config: AppConfig, config_path: Path, name: str) -> RegisterResult:
    """Stop using the LLM client of package *name*: back to the default provider.

    Removes ``provider``, ``class_path`` and ``package`` from ``llm_config``, the custom
    provider's ``extra_models``, and ``model`` and ``agent_models`` entries that name
    one of them. A package without configured agents is deactivated. Project overrides
    stay as they are.

    Raises:
        PackageConflict: The config file does not take the LLM client from *name*.
        PackageInvalid: The config without the client would not be valid.
    """
    section = read_config_file(config_path)
    if package_llm_client(section, name) is None:
        raise PackageConflict(f"{name} does not provide the LLM client")
    llm = _llm_section(section)
    models = set(_custom_models(section))

    edits: dict[str, Any] = {
        join_path(["llm_config", key]): None for key in ("provider", "class_path", "package")
    }
    _remove_keys(edits, ["llm_config", "extra_models"], llm.get("extra_models"), models)
    if llm.get("model") in models:
        edits[join_path(["llm_config", "model"])] = None
    agent_models = llm.get("agent_models")
    if isinstance(agent_models, dict):
        pointing = {agent for agent, model in agent_models.items() if model in models}
        _remove_keys(edits, ["llm_config", "agent_models"], agent_models, pointing)

    manifest = load_manifest(config.agent_packages.dir)
    new_manifest = manifest.model_copy(deep=True)
    if name in new_manifest.packages and not _package_agents(section, name):
        new_manifest.set_active(name, None)
    return _with_packages_restart(_apply(config, config_path, manifest, new_manifest, {}, edits))


def delete_version(packages_dir: Path, name: str, version: str) -> None:
    """Delete an uploaded version: its manifest entry, wheel and unpacked files.

    Raises:
        PackageNotFound: The version is not uploaded.
        PackageConflict: The version is active or is the one loaded at startup.
    """
    manifest = load_manifest(packages_dir)
    entry = _version(manifest, name, version)
    if entry.active:
        raise PackageConflict(f"{name} {version} is active")
    if loaded.loaded_version(name) == version:
        raise PackageConflict(f"{name} {version} is in use until the service restarts")

    wheel = wheel_path(packages_dir, entry.filename)
    site = site_dir(packages_dir, name, version)
    del manifest.packages[name][version]
    if not manifest.packages[name]:
        del manifest.packages[name]
    save_manifest(packages_dir, manifest)
    wheel.unlink(missing_ok=True)
    _remove_dir(site)
