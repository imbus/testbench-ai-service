"""Run the package inspection (``inspector.py``) in a subprocess and read its report."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from pydantic import ValidationError

import testbench_ai_service
from testbench_ai_service.agent_packages.models import InspectionReport

INSPECT_TIMEOUT_SECONDS = 30
_STDERR_TAIL = 2000

#: What the child needs to start, find its libraries and write temporary files. Compared in
#: upper case: Windows names are case-insensitive.
_ENV_KEEP = frozenset(
    {
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "SYSTEMDRIVE",
        "WINDIR",
        "COMSPEC",
        "TEMP",
        "TMP",
        "TMPDIR",
        "HOME",
        "USERPROFILE",
        "HOMEDRIVE",
        "HOMEPATH",
        "APPDATA",
        "LOCALAPPDATA",
        "PROGRAMDATA",
        "USERNAME",
        "USER",
        "LOGNAME",
        "LANG",
        "LANGUAGE",
        "TZ",
        "NUMBER_OF_PROCESSORS",
        "PROCESSOR_ARCHITECTURE",
        "VIRTUAL_ENV",
        "LD_LIBRARY_PATH",
        "DYLD_LIBRARY_PATH",
        "DYLD_FALLBACK_LIBRARY_PATH",
    }
)
#: Locale settings, interpreter switches and what the binary's bootloader hands to its children.
_ENV_KEEP_PREFIXES = ("LC_", "PYTHON", "_PYI_", "_MEI")


def _frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def inspection_command(site_dir: Path) -> list[str]:
    """The command that inspects *site_dir*: the hidden CLI command of the binary, or the
    inspector module of the running source tree.

    ``-s`` drops the user site directory. ``-I`` is not used: it would also drop the
    working directory from ``sys.path`` and import an installed copy of the service
    instead of the running one.
    """
    if _frozen():
        return [sys.executable, "inspect-agent-package", str(site_dir)]
    return [
        sys.executable,
        "-s",
        "-m",
        "testbench_ai_service.agent_packages.inspector",
        str(site_dir),
    ]


def inspection_env() -> dict[str, str]:
    """The environment of the inspection process: the service's, reduced to what a Python
    process needs.

    The child imports code of a package nobody has registered yet, so it must not see the
    service's credentials. Those have no fixed names (``<PROJECT>_<PROVIDER>_API_KEY``,
    whatever ``.env`` holds), so the variables to keep are listed, not the ones to drop.
    ``PYTHONPATH`` goes too: it would put foreign code in front of the service's.
    """
    env = {
        name: value
        for name, value in os.environ.items()
        if name.upper() in _ENV_KEEP or name.upper().startswith(_ENV_KEEP_PREFIXES)
    }
    for name in [name for name in env if name.upper() == "PYTHONPATH"]:
        del env[name]
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _failed(message: str) -> InspectionReport:
    return InspectionReport(ok=False, errors=[message])


def run_inspection(site_dir: Path, timeout: float = INSPECT_TIMEOUT_SECONDS) -> InspectionReport:
    """Inspect the package unpacked in *site_dir* in a subprocess.

    Never raises: a timeout, a crash or unreadable output becomes a failed report.
    """
    # From source, the running service's package must be first on the child's sys.path.
    cwd = None if _frozen() else Path(testbench_ai_service.__file__).resolve().parent.parent
    try:
        completed = subprocess.run(
            inspection_command(site_dir),
            capture_output=True,
            timeout=timeout,
            cwd=cwd,
            env=inspection_env(),
            check=False,
        )
    except subprocess.TimeoutExpired:
        return _failed(f"The inspection timed out after {timeout:g} seconds.")
    except OSError as e:
        return _failed(f"The inspection could not be started: {e}")

    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", errors="replace").strip()[-_STDERR_TAIL:]
        return _failed(f"The inspection failed with exit code {completed.returncode}: {stderr}")
    try:
        return InspectionReport.model_validate_json(completed.stdout)
    except ValidationError as e:
        return _failed(f"The inspection returned invalid output: {e}")
