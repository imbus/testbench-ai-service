import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

from testbench_ai_service.webui.security import is_loopback, resolve_within


@pytest.fixture
def base(tmp_path: Path) -> Path:
    (tmp_path / "de" / "reviewer").mkdir(parents=True)
    (tmp_path / "de" / "reviewer" / "prompt.yaml").write_text("name: x", encoding="utf-8")
    (tmp_path / "outside.txt").write_text("secret", encoding="utf-8")
    return tmp_path / "de"


def test_allows_nested_relative_path(base: Path):
    assert resolve_within(base, "reviewer/prompt.yaml") == (
        base / "reviewer" / "prompt.yaml"
    ).resolve()


def test_allows_the_base_itself(base: Path):
    assert resolve_within(base, ".") == base.resolve()


def test_rejects_parent_traversal(base: Path):
    with pytest.raises(HTTPException) as exc:
        resolve_within(base, "../outside.txt")
    assert exc.value.status_code == 400


def test_rejects_deep_traversal(base: Path):
    with pytest.raises(HTTPException):
        resolve_within(base, "reviewer/../../../../etc/passwd")


def test_rejects_absolute_path_outside_base(base: Path, tmp_path: Path):
    with pytest.raises(HTTPException):
        resolve_within(base, tmp_path / "outside.txt")


def test_accepts_absolute_path_inside_base(base: Path):
    inside = base / "reviewer" / "prompt.yaml"
    assert resolve_within(base, inside) == inside.resolve()


def test_rejects_prefix_sibling_directory(tmp_path: Path):
    """`/prompts-evil` must not pass a containment check against `/prompts`."""
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts-evil").mkdir()
    with pytest.raises(HTTPException):
        resolve_within(tmp_path / "prompts", tmp_path / "prompts-evil")


@pytest.mark.skipif(
    sys.platform == "win32", reason="symlink creation needs privileges on Windows"
)
def test_rejects_symlink_escaping_the_base(base: Path, tmp_path: Path):
    (base / "escape").symlink_to(tmp_path / "outside.txt")
    with pytest.raises(HTTPException):
        resolve_within(base, "escape")


def test_rejects_empty_candidate(base: Path):
    with pytest.raises(HTTPException):
        resolve_within(base, "")


@pytest.mark.parametrize("host", ["127.0.0.1", "::1", "localhost", "127.0.0.5"])
def test_loopback_hosts(host: str):
    assert is_loopback(host) is True


@pytest.mark.parametrize("host", ["10.0.0.4", "192.168.1.9", "example.com", None, ""])
def test_non_loopback_hosts(host):
    assert is_loopback(host) is False
