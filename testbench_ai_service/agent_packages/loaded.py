"""Which agent packages this process put on ``sys.path`` at startup.

Package code may only run in the service process after the package was
registered and the service restarted. ``activate_packages`` is therefore called
before the config is validated at every (re)start; nothing else adds package
directories to ``sys.path``. A restart from the console runs in the same process
(see ``testbench_ai_service.restart``), so a second call swaps a changed version:
the old version's directory leaves ``sys.path`` and its modules leave
``sys.modules`` before the new one is put in place. A package that is not loaded is validated against
its stored inspection report instead (see ``agent_info``).
"""

from __future__ import annotations

import hashlib
import importlib
import sys
from pathlib import Path

from testbench_ai_service.agent_packages.manifest import (
    ManifestError,
    load_manifest,
    site_dir,
    wheel_path,
)
from testbench_ai_service.log import logger

_CHUNK = 1024 * 1024

#: package name -> (loaded version, sys.path entry)
_loaded: dict[str, tuple[str, str]] = {}
#: package name -> reason it is not usable
_failures: dict[str, str] = {}
#: agent key -> reason its class failed to import at startup
_agent_failures: dict[str, str] = {}


def _sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK):
            hasher.update(chunk)
    return hasher.hexdigest()


def _activate(packages_dir: Path, name: str, version: str, filename: str, sha256: str) -> str:
    """Put one package version on ``sys.path``; return the path entry.

    Raises:
        ValueError: The stored wheel or the unpacked directory is missing or
            the wheel does not match the recorded hash.
    """
    try:
        wheel = wheel_path(packages_dir, filename)
        site = site_dir(packages_dir, name, version)
    except Exception as e:  # resolve_within raises HTTPException for an unsafe name
        raise ValueError(f"invalid package location: {getattr(e, 'detail', e)}") from e
    if not wheel.is_file():
        raise ValueError(f"the wheel '{filename}' is missing")
    if _sha256(wheel) != sha256:
        raise ValueError(f"the wheel '{filename}' does not match its recorded hash")
    if not site.is_dir():
        raise ValueError(f"the unpacked directory of version {version} is missing")
    entry = str(site)
    sys.path.insert(0, entry)
    return entry


def _unload(path_entry: str) -> None:
    """Take a package directory off ``sys.path`` and drop the modules imported from it.

    Code that still holds a reference to an old module or class keeps it; the
    next import resolves against the new ``sys.path``.
    """
    while path_entry in sys.path:
        sys.path.remove(path_entry)
    root = Path(path_entry).resolve()
    for module_name, module in list(sys.modules.items()):
        module_file = getattr(module, "__file__", None)
        if module_file:
            if Path(module_file).resolve().is_relative_to(root):
                del sys.modules[module_name]
            continue
        # A namespace package (e.g. a shared top-level name) has no __file__.
        search = getattr(module, "__path__", None)
        if search is not None and any(Path(p).resolve().is_relative_to(root) for p in search):
            del sys.modules[module_name]
    importlib.invalidate_caches()


def activate_packages(packages_dir: Path) -> list[str]:
    """Put the active version of every registered package on ``sys.path``.

    Only versions whose stored wheel still matches the recorded ``sha256`` are
    loaded. Problems are logged and returned; they never stop the startup.

    Called again by an in-process restart: a package whose active version is
    unchanged stays as it is, one whose version changed or that is no longer
    active is unloaded first. Failures are recorded afresh.
    """
    _failures.clear()
    _agent_failures.clear()
    try:
        manifest = load_manifest(packages_dir)
    except ManifestError as e:
        message = f"Agent packages are not loaded: the manifest is unreadable: {e}"
        logger.error(message)
        return [message]

    for name, (version, path_entry) in list(_loaded.items()):
        entry = manifest.active(name) if name in manifest.packages else None
        if entry is None or entry.version != version:
            _unload(path_entry)
            del _loaded[name]
            logger.info("Unloaded agent package '%s' %s", name, version)

    errors: list[str] = []
    for name in manifest.packages:
        entry = manifest.active(name)
        if entry is None or name in _loaded:
            continue
        try:
            path_entry = _activate(packages_dir, name, entry.version, entry.filename, entry.sha256)
        except (ValueError, OSError) as e:
            message = f"Agent package '{name}' {entry.version} is not loaded: {e}"
            logger.error(message)
            mark_failed(name, message)
            errors.append(message)
            continue
        _loaded[name] = (entry.version, path_entry)
        logger.info("Loaded agent package '%s' %s", name, entry.version)
    return errors


def is_loaded(name: str) -> bool:
    """Whether *name* was put on ``sys.path`` at startup and has not failed since."""
    return name in _loaded and name not in _failures


def loaded_version(name: str) -> str | None:
    """The version of *name* put on ``sys.path`` at startup, if any."""
    loaded = _loaded.get(name)
    return loaded[0] if loaded else None


def mark_failed(name: str, reason: str) -> None:
    """Record that package *name* could not be loaded at startup (e.g. hash mismatch)."""
    _failures[name] = reason


def failures() -> dict[str, str]:
    """Package name to the reason it is not usable."""
    return dict(_failures)


def mark_agent_failed(agent_key: str, reason: str) -> None:
    """Record that the class of agent *agent_key* failed to import at startup."""
    _agent_failures[agent_key] = reason


def agent_failures() -> dict[str, str]:
    """Agent key to the reason its class failed to import at startup."""
    return dict(_agent_failures)


def reset() -> None:
    """Forget everything and undo the ``sys.path`` changes. Only for tests.

    Modules imported from a package directory are dropped from ``sys.modules``
    as well, so the next test does not see them.
    """
    for path_entry in {path_entry for _version, path_entry in _loaded.values()}:
        _unload(path_entry)
    _loaded.clear()
    _failures.clear()
    _agent_failures.clear()
