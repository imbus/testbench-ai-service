"""The documented example package builds into a wheel the inspection accepts."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from testbench_ai_service.agent_packages.runner import run_inspection
from tests.helpers.wheels import build_wheel, extracted

EXAMPLE = Path(__file__).resolve().parents[3] / "examples" / "agent_package"
MODULE = "acme_rater"
ENTRY_POINTS = {"acme_rater": f"{MODULE}.agent:RaterAgent"}


def _package_files() -> dict[str, str | bytes]:
    files: dict[str, str | bytes] = {}
    for path in sorted((EXAMPLE / MODULE).rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            files[path.relative_to(EXAMPLE).as_posix()] = path.read_bytes()
    return files


def test_example_package_is_accepted(tmp_path):
    files = _package_files()
    assert f"{MODULE}/agent.py" in files
    site = extracted(tmp_path, files, name="acme-rater", entry_points=ENTRY_POINTS)
    report = run_inspection(site)
    assert report.ok is True, report
    assert report.agents["acme_rater"].ok


def test_example_package_builds_a_wheel(tmp_path):
    wheel = build_wheel(
        tmp_path, name="acme-rater", files=_package_files(), entry_points=ENTRY_POINTS
    )
    assert wheel.exists()


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_example_package_files_are_not_git_ignored():
    """A fresh clone must contain the example's prompts and templates."""
    repo = EXAMPLE.parents[1]
    paths = [
        path.relative_to(repo).as_posix()
        for path in sorted((EXAMPLE / MODULE).rglob("*"))
        if path.is_file() and "__pycache__" not in path.parts
    ]
    assert any("/prompts/" in path for path in paths)
    assert any("/templates/" in path for path in paths)
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", *paths],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 128:
        pytest.skip("not a git checkout")
    assert result.stdout.strip() == ""
