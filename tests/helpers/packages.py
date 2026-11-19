"""Lay out an agent packages directory (wheel, unpacked site, manifest) for tests."""

from __future__ import annotations

import hashlib
import shutil
from datetime import datetime, timezone
from pathlib import Path

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
    PackageVersion,
)
from testbench_ai_service.agent_packages.wheel import extract_wheel
from tests.helpers.wheels import VALID_AGENT_FILES, VALID_ENTRY_POINTS, build_wheel

PACKAGE = "acme-tb-agents"
CLASS_PATH = "acme.rater.agent.RaterAgent"


def rater_report(**overrides) -> AgentReport:
    """The report the inspector would write for the ``acme_rater`` test agent."""
    values = {
        "entry_point": "acme.rater.agent:RaterAgent",
        "class_path": CLASS_PATH,
        "ok": True,
        "data_fields": ["title"],
        "context_sample": {"title": "<str>"},
    }
    values.update(overrides)
    return AgentReport(**values)


LLM_CLASS_PATH = "acme_llm.client.AcmeClient"


def llm_report(**overrides) -> LLMClientReport:
    """The report the inspector would write for the ``acme_llm`` test client."""
    values = {"entry_point": "acme_llm.client:AcmeClient", "class_path": LLM_CLASS_PATH, "ok": True}
    values.update(overrides)
    return LLMClientReport(**values)


def install_package(
    packages_dir: Path,
    *,
    name: str = PACKAGE,
    version: str = "1.0.0",
    report: AgentReport | None = None,
    active: bool = True,
    sha256: str | None = None,
    files: dict[str, str | bytes] | None = None,
    entry_points: dict[str, str] | None = None,
    reports: dict[str, AgentReport] | None = None,
    llm_entry_points: dict[str, str] | None = None,
    llm_clients: dict[str, LLMClientReport] | None = None,
) -> PackageVersion:
    """Store a wheel of the valid test agent, unpack it and record it in the manifest.

    ``sha256`` overrides the recorded hash, e.g. to simulate a tampered wheel.
    ``files``, ``entry_points`` and ``reports`` replace the single valid agent.
    """
    build_dir = packages_dir.parent / f"build-{name}-{version}"
    build_dir.mkdir(parents=True, exist_ok=True)
    built = build_wheel(
        build_dir,
        name=name,
        version=version,
        files=files if files is not None else VALID_AGENT_FILES,
        entry_points=entry_points if entry_points is not None else VALID_ENTRY_POINTS,
        llm_entry_points=llm_entry_points,
    )
    stored = wheel_path(packages_dir, built.name)
    stored.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(built, stored)
    target = site_dir(packages_dir, name, version)
    target.parent.mkdir(parents=True, exist_ok=True)
    extract_wheel(stored, target)

    entry = PackageVersion(
        name=name,
        version=version,
        filename=built.name,
        sha256=sha256 or hashlib.sha256(stored.read_bytes()).hexdigest(),
        size=stored.stat().st_size,
        uploaded_at=datetime(2026, 11, 17, tzinfo=timezone.utc),
        active=active,
        report=InspectionReport(
            ok=True,
            agents=reports
            if reports is not None
            else {"acme_rater": report if report is not None else rater_report()},
            llm_clients=llm_clients or {},
        ),
    )
    manifest = load_manifest(packages_dir)
    manifest.packages.setdefault(name, {})[version] = entry
    if active:
        manifest.set_active(name, version)
    save_manifest(packages_dir, manifest)
    return entry


BROKEN_CLASS_PATH = "acme.broken.BrokenAgent"

#: The valid ``acme_rater`` agent plus ``acme_broken``, whose module calls sys.exit() on import.
TWO_AGENT_FILES: dict[str, str | bytes] = {
    **VALID_AGENT_FILES,
    "acme/broken.py": "import sys\n\nsys.exit(3)\n",
}
TWO_AGENT_ENTRY_POINTS = {**VALID_ENTRY_POINTS, "acme_broken": "acme.broken:BrokenAgent"}


def install_two_agent_package(packages_dir: Path) -> PackageVersion:
    """A package with a working and a broken agent, both listed in the report."""
    return install_package(
        packages_dir,
        files=TWO_AGENT_FILES,
        entry_points=TWO_AGENT_ENTRY_POINTS,
        reports={
            "acme_rater": rater_report(),
            "acme_broken": rater_report(
                entry_point="acme.broken:BrokenAgent", class_path=BROKEN_CLASS_PATH
            ),
        },
    )
