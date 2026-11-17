"""Console routes to upload agent packages (wheels) and configure their agents."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from testbench_ai_service.agent_packages import loaded
from testbench_ai_service.agent_packages.manifest import ManifestError, load_manifest
from testbench_ai_service.agent_packages.models import Manifest, PackageVersion
from testbench_ai_service.agent_packages.service import (
    DefaultDirs,
    FileConflicts,
    PackageConflict,
    PackageInvalid,
    PackageNotFound,
    PackageTooLarge,
    RegisterAgent,
    RegisterResult,
    activate_version,
    delete_version,
    register_agents,
    remove_package,
    store_upload,
    uses_default_dirs,
)
from testbench_ai_service.config import AppConfig
from testbench_ai_service.dependencies import get_app_config
from testbench_ai_service.log import logger
from testbench_ai_service.webui.auth import (
    bind_log_user,
    current_session,
    require_admin,
    require_csrf,
)
from testbench_ai_service.webui.config_io import read_config_file
from testbench_ai_service.webui.security import require_loopback
from testbench_ai_service.webui.session import Session
from testbench_ai_service.webui.write_lock import get_write_lock

router = APIRouter(
    prefix="/admin/api/agent-packages",
    dependencies=[Depends(require_loopback)],
)

_T = TypeVar("_T")
_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*$")
_UPLOAD_DISABLED = "Uploading agent packages is disabled (agent_packages.allow_upload)."


class PackageView(BaseModel):
    """One uploaded agent package as the console lists it."""

    name: str
    versions: list[PackageVersion]
    registered: dict[str, str] = Field(
        default_factory=dict,
        description="Agent key to entry point, for the agents in config.toml on disk.",
    )
    loaded: bool
    load_error: str | None = None


class PackagesResponse(BaseModel):
    allow_upload: bool
    default_dirs: bool
    packages: list[PackageView]


class RegisterPackageRequest(BaseModel):
    agents: list[RegisterAgent] = Field(min_length=1)
    overwrite: list[str] = Field(default_factory=list)
    keep: list[str] = Field(default_factory=list)


class ActivatePackageRequest(BaseModel):
    overwrite: list[str] = Field(default_factory=list)
    keep: list[str] = Field(default_factory=list)


def _segment(value: str, what: str) -> str:
    if not _SAFE_SEGMENT.match(value) or ".." in value:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"Invalid package {what}")
    return value


def _http_error(exc: Exception) -> HTTPException:
    """Translate a package service error into the HTTP error the console shows."""
    if isinstance(exc, DefaultDirs):
        return HTTPException(
            status.HTTP_409_CONFLICT, detail={"code": "default_dirs", "message": str(exc)}
        )
    if isinstance(exc, FileConflicts):
        return HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "file_conflicts",
                "message": "Some files already exist with other content.",
                "conflicts": [conflict.model_dump() for conflict in exc.conflicts],
            },
        )
    if isinstance(exc, PackageConflict):
        return HTTPException(status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, PackageNotFound):
        return HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, PackageInvalid):
        return HTTPException(
            413 if isinstance(exc, PackageTooLarge) else 422,
            detail={
                "message": str(exc),
                "issues": [issue.model_dump() for issue in exc.issues],
            },
        )
    logger.error("Agent package manifest is unusable: %s", exc)
    return HTTPException(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="The agent package manifest could not be read; see the service log.",
    )


async def _run(func: Callable[..., _T], *args: Any) -> _T:
    """Run a blocking service call in the threadpool and map its errors to HTTP ones.

    An ``HTTPException`` raised by the service (path checks, config file errors) passes through.
    """
    try:
        return await run_in_threadpool(func, *args)
    except (
        DefaultDirs,
        FileConflicts,
        PackageConflict,
        PackageNotFound,
        PackageInvalid,
        ManifestError,
    ) as e:
        raise _http_error(e) from e


def _registered(manifest: Manifest, name: str, disk_agents: dict[str, Any]) -> dict[str, str]:
    """Agent key to entry point of the agents in the config file that belong to *name*."""
    active = manifest.active(name)
    by_class = (
        {report.class_path: entry for entry, report in active.report.agents.items()}
        if active
        else {}
    )
    result: dict[str, str] = {}
    for key, agent in disk_agents.items():
        if isinstance(agent, dict) and agent.get("package") == name:
            class_path = str(agent.get("class_path", ""))
            result[key] = by_class.get(class_path, class_path)
    return result


def _read_packages(config: AppConfig, config_path: Path) -> PackagesResponse:
    manifest = load_manifest(config.agent_packages.dir)
    disk_agents = read_config_file(config_path).get("agents") or {}
    failures = loaded.failures()
    packages = [
        PackageView(
            name=name,
            versions=sorted(versions.values(), key=lambda v: v.uploaded_at, reverse=True),
            registered=_registered(manifest, name, disk_agents),
            loaded=loaded.is_loaded(name),
            load_error=failures.get(name),
        )
        for name, versions in sorted(manifest.packages.items())
    ]
    return PackagesResponse(
        allow_upload=config.agent_packages.allow_upload,
        default_dirs=uses_default_dirs(config),
        packages=packages,
    )


@router.get("", response_model=PackagesResponse)
async def list_packages(
    request: Request,
    _: Session = Depends(current_session),
    config: AppConfig = Depends(get_app_config),
) -> PackagesResponse:
    """The uploaded packages with their versions, inspection reports and configured agents."""
    return await _run(_read_packages, config, Path(request.app.state.config_path))


@router.post("", response_model=PackageVersion)
async def upload_package(
    file: UploadFile = File(...),
    session: Session = Depends(require_admin),
    _csrf: None = Depends(require_csrf),
    _log: Session = Depends(bind_log_user),
    config: AppConfig = Depends(get_app_config),
    lock: asyncio.Lock = Depends(get_write_lock),
) -> PackageVersion:
    """Store a wheel, unpack and inspect it. The new version is not active yet."""
    settings = config.agent_packages
    if not settings.allow_upload:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=_UPLOAD_DISABLED)
    max_bytes = settings.max_upload_mb * 1024 * 1024
    async with lock:
        entry = await _run(
            store_upload, settings.dir, file.filename or "", file.file, max_bytes, session.username
        )
    logger.info("Uploaded agent package %s %s (sha256 %s)", entry.name, entry.version, entry.sha256)
    return entry


@router.post("/{name}/{version}/register", response_model=RegisterResult)
async def register_package_agents(
    name: str,
    version: str,
    body: RegisterPackageRequest,
    request: Request,
    _: Session = Depends(require_admin),
    _csrf: None = Depends(require_csrf),
    _log: Session = Depends(bind_log_user),
    config: AppConfig = Depends(get_app_config),
    lock: asyncio.Lock = Depends(get_write_lock),
) -> RegisterResult:
    """Configure entry points of a package version as agents and activate the version."""
    _segment(name, "name")
    _segment(version, "version")
    config_path = Path(request.app.state.config_path)
    async with lock:
        result = await _run(
            register_agents,
            config,
            config_path,
            name,
            version,
            body.agents,
            body.overwrite,
            body.keep,
        )
    logger.info(
        "Registered agents %s from agent package %s %s",
        ", ".join(agent.agent_key for agent in body.agents),
        name,
        version,
    )
    return result


@router.post("/{name}/{version}/activate", response_model=RegisterResult)
async def activate_package_version(
    name: str,
    version: str,
    body: ActivatePackageRequest,
    request: Request,
    _: Session = Depends(require_admin),
    _csrf: None = Depends(require_csrf),
    _log: Session = Depends(bind_log_user),
    config: AppConfig = Depends(get_app_config),
    lock: asyncio.Lock = Depends(get_write_lock),
) -> RegisterResult:
    """Make a version the active one; it is loaded at the next start."""
    _segment(name, "name")
    _segment(version, "version")
    config_path = Path(request.app.state.config_path)
    async with lock:
        result = await _run(
            activate_version, config, config_path, name, version, body.overwrite, body.keep
        )
    logger.info("Activated agent package %s %s", name, version)
    return result


@router.delete("/{name}/{version}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_package_version(
    name: str,
    version: str,
    _: Session = Depends(require_admin),
    _csrf: None = Depends(require_csrf),
    _log: Session = Depends(bind_log_user),
    config: AppConfig = Depends(get_app_config),
    lock: asyncio.Lock = Depends(get_write_lock),
) -> Response:
    """Delete an uploaded version that is neither active nor in use."""
    _segment(name, "name")
    _segment(version, "version")
    async with lock:
        await _run(delete_version, config.agent_packages.dir, name, version)
    logger.info("Deleted agent package %s %s", name, version)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{name}", response_model=RegisterResult)
async def remove_package_agents(
    name: str,
    request: Request,
    _: Session = Depends(require_admin),
    _csrf: None = Depends(require_csrf),
    _log: Session = Depends(bind_log_user),
    config: AppConfig = Depends(get_app_config),
    lock: asyncio.Lock = Depends(get_write_lock),
) -> RegisterResult:
    """Remove the agents of a package from the config and deactivate the package."""
    _segment(name, "name")
    config_path = Path(request.app.state.config_path)
    async with lock:
        result = await _run(remove_package, config, config_path, name)
    logger.info("Removed the agents of agent package %s", name)
    return result
