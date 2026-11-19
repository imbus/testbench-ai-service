"""The documented example LLM client package builds into a wheel the inspection accepts."""

from __future__ import annotations

from pathlib import Path

from testbench_ai_service.agent_packages.runner import run_inspection
from tests.helpers.wheels import extracted

EXAMPLE = Path(__file__).resolve().parents[3] / "examples" / "llm_client_package"
MODULE = "acme_llm"
ENTRY_POINTS = {"acme_llm": f"{MODULE}.client:AcmeLLMClient"}


def _package_files() -> dict[str, str | bytes]:
    files: dict[str, str | bytes] = {}
    for path in sorted((EXAMPLE / MODULE).rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            files[path.relative_to(EXAMPLE).as_posix()] = path.read_bytes()
    return files


def test_example_llm_client_package_is_accepted(tmp_path):
    files = _package_files()
    assert f"{MODULE}/client.py" in files
    site = extracted(
        tmp_path, files, name="acme-llm", entry_points={}, llm_entry_points=ENTRY_POINTS
    )
    report = run_inspection(site)
    assert report.ok is True, report
    assert report.llm_clients["acme_llm"].ok


def test_the_example_declares_the_entry_point_the_test_uses():
    pyproject = (EXAMPLE / "pyproject.toml").read_text(encoding="utf-8")
    assert '[project.entry-points."testbench_ai_service.llm_clients"]' in pyproject
    assert 'acme_llm = "acme_llm.client:AcmeLLMClient"' in pyproject
