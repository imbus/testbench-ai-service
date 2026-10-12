import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from build_binary import build_frontend


@pytest.fixture
def frontend(tmp_path: Path) -> Path:
    directory = tmp_path / "frontend"
    directory.mkdir()
    (directory / "package.json").write_text("{}", encoding="utf-8")
    return directory


def test_runs_ci_then_build(frontend: Path):
    with patch("build_binary.subprocess.run") as run:
        run.return_value = MagicMock(returncode=0)
        build_frontend(frontend)
    commands = [call.args[0] for call in run.call_args_list]
    assert any("ci" in command for command in commands)
    assert any("build" in command for command in commands)


def test_skip_flag_runs_nothing(frontend: Path):
    with patch("build_binary.subprocess.run") as run:
        build_frontend(frontend, skip=True)
    run.assert_not_called()


def test_missing_node_fails_loudly(frontend: Path):
    with (
        patch("build_binary.subprocess.run", side_effect=FileNotFoundError),
        pytest.raises(SystemExit) as exc,
    ):
        build_frontend(frontend)
    assert "Node" in str(exc.value)


def test_failing_build_aborts(frontend: Path):
    error = subprocess.CalledProcessError(1, ["npm", "run", "build"])
    with patch("build_binary.subprocess.run", side_effect=error), pytest.raises(SystemExit):
        build_frontend(frontend)


def test_absent_frontend_directory_aborts(tmp_path: Path):
    with pytest.raises(SystemExit):
        build_frontend(tmp_path / "nope")
