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


def _failed(message: str) -> InspectionReport:
    return InspectionReport(ok=False, errors=[message])


def run_inspection(site_dir: Path, timeout: float = INSPECT_TIMEOUT_SECONDS) -> InspectionReport:
    """Inspect the package unpacked in *site_dir* in a subprocess.

    Never raises: a timeout, a crash or unreadable output becomes a failed report.
    """
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["PYTHONIOENCODING"] = "utf-8"
    # From source, the running service's package must be first on the child's sys.path.
    cwd = None if _frozen() else Path(testbench_ai_service.__file__).resolve().parent.parent
    try:
        completed = subprocess.run(
            inspection_command(site_dir),
            capture_output=True,
            timeout=timeout,
            cwd=cwd,
            env=env,
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
