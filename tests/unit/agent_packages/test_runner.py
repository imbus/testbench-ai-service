from __future__ import annotations

import os
import sys
from pathlib import Path

from testbench_ai_service.agent_packages import runner
from testbench_ai_service.agent_packages.runner import inspection_command, run_inspection
from tests.helpers.wheels import VALID_AGENT_FILES, extracted


def test_inspection_command_frozen(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    command = inspection_command(Path("x"))
    assert command == [sys.executable, "inspect-agent-package", "x"]


def test_inspection_command_from_source(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    command = inspection_command(Path("x"))
    assert command[0] == sys.executable
    assert "-s" in command
    assert "-I" not in command
    assert command[-3:] == ["-m", "testbench_ai_service.agent_packages.inspector", "x"]


def test_run_inspection_times_out(tmp_path):
    marker = tmp_path / "loop-started"
    source = f"from pathlib import Path\nPath({str(marker)!r}).touch()\nwhile True:\n    pass\n"
    files = {**VALID_AGENT_FILES, "acme/rater/agent.py": source}
    # Long enough for the child to import the service before it reaches the loop.
    report = run_inspection(extracted(tmp_path, files), timeout=10)
    assert not report.ok
    assert "timed out" in report.errors[0]
    # The child reached the agent's module, so it was the loop that timed out.
    assert marker.exists()


def test_run_inspection_reports_failed_process(monkeypatch):
    monkeypatch.setattr(
        runner,
        "inspection_command",
        lambda site: [sys.executable, "-c", "import sys; sys.stderr.write('bad'); sys.exit(3)"],
    )
    report = run_inspection(Path("x"))
    assert not report.ok
    assert "exit code 3" in report.errors[0]
    assert "bad" in report.errors[0]


def test_run_inspection_reports_invalid_output(monkeypatch):
    monkeypatch.setattr(
        runner, "inspection_command", lambda site: [sys.executable, "-c", "print('nope')"]
    )
    report = run_inspection(Path("x"))
    assert not report.ok
    assert "invalid" in report.errors[0]


def test_run_inspection_drops_pythonpath(monkeypatch, tmp_path):
    monkeypatch.setenv("PYTHONPATH", str(tmp_path))
    script = "import os; print('{\"ok\": %s}' % str('PYTHONPATH' not in os.environ).lower())"
    monkeypatch.setattr(runner, "inspection_command", lambda site: [sys.executable, "-c", script])
    assert run_inspection(Path("x")).ok


def test_inspection_env_keeps_only_what_python_needs(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret")
    monkeypatch.setenv("MYPROJECT_AZURE_CLIENT_SECRET", "secret")
    monkeypatch.setenv("SOME_UNRELATED_SETTING", "value")
    monkeypatch.setenv("PYTHONPATH", "somewhere")
    monkeypatch.setenv("PYTHONUTF8", "1")
    monkeypatch.setenv("LC_ALL", "C.UTF-8")
    env = runner.inspection_env()
    assert "OPENAI_API_KEY" not in env
    assert "MYPROJECT_AZURE_CLIENT_SECRET" not in env
    assert "SOME_UNRELATED_SETTING" not in env
    assert "PYTHONPATH" not in env
    assert env["PYTHONUTF8"] == "1"
    assert env["LC_ALL"] == "C.UTF-8"
    assert env["PYTHONIOENCODING"] == "utf-8"
    assert env["PATH"] == os.environ["PATH"]


def test_inspected_package_does_not_see_credentials(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret")
    seen = tmp_path / "seen"
    source = (
        "import os\nfrom pathlib import Path\n"
        f"Path({str(seen)!r}).write_text(os.environ.get('OPENAI_API_KEY', 'absent'))\n"
        + str(VALID_AGENT_FILES["acme/rater/agent.py"])
    )
    files = {**VALID_AGENT_FILES, "acme/rater/agent.py": source}
    report = run_inspection(extracted(tmp_path, files))
    assert report.ok, report.errors
    assert seen.read_text() == "absent"


def test_inspection_does_not_import_into_service(tmp_path):
    run_inspection(extracted(tmp_path, VALID_AGENT_FILES))
    assert "acme" not in sys.modules
    assert str(tmp_path / "site") not in sys.path
