from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

from testbench_ai_service.config import AppConfig
from testbench_ai_service.dependencies import get_app_config
from testbench_ai_service.models.webui import AdminUiConfig
from testbench_ai_service.webui.security import is_loopback, require_loopback, resolve_within


@pytest.fixture
def base(tmp_path: Path) -> Path:
    (tmp_path / "de" / "reviewer").mkdir(parents=True)
    (tmp_path / "de" / "reviewer" / "prompt.yaml").write_text("name: x", encoding="utf-8")
    (tmp_path / "outside.txt").write_text("secret", encoding="utf-8")
    return tmp_path / "de"


def test_allows_nested_relative_path(base: Path):
    assert (
        resolve_within(base, "reviewer/prompt.yaml")
        == (base / "reviewer" / "prompt.yaml").resolve()
    )


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


def test_rejects_symlink_escaping_the_base(base: Path, tmp_path: Path):
    link = base / "escape"
    try:
        link.symlink_to(tmp_path / "outside.txt")
    except OSError:
        # Symlink creation needs elevated privileges on some locked-down hosts.
        # This is a capability probe, not a platform check: on a machine where
        # it works (this one included), the test actually runs.
        pytest.skip("symlink creation is not permitted on this host")
    with pytest.raises(HTTPException):
        resolve_within(base, "escape")


def test_rejects_empty_candidate(base: Path):
    with pytest.raises(HTTPException):
        resolve_within(base, "")


def test_rejects_nul_byte_in_candidate(base: Path):
    """A NUL byte must surface as the 400 this chokepoint promises, not an
    unhandled 500 from a downstream open() raising ValueError."""
    with pytest.raises(HTTPException) as exc:
        resolve_within(base, "reviewer/prompt\x00.yaml")
    assert exc.value.status_code == 400


@pytest.mark.parametrize(
    "host",
    ["127.0.0.1", "::1", "localhost", "127.0.0.5", "::ffff:127.0.0.1"],
)
def test_loopback_hosts(host: str):
    assert is_loopback(host) is True


@pytest.mark.parametrize(
    "host",
    ["10.0.0.4", "192.168.1.9", "example.com", None, "", "::ffff:10.0.0.4"],
)
def test_non_loopback_hosts(host):
    assert is_loopback(host) is False


def _stub_app(*, require_loopback_enabled: bool, client: tuple[str, int] | None):
    with patch("testbench_ai_service.config.validate_tb_server_url"):
        stub_config = AppConfig(admin_ui=AdminUiConfig(require_loopback=require_loopback_enabled))

    app = FastAPI()
    app.dependency_overrides[get_app_config] = lambda: stub_config

    @app.get("/probe")
    def probe(_: None = Depends(require_loopback)):
        return {"ok": True}

    return TestClient(app, client=client)


def test_require_loopback_is_a_noop_when_disabled():
    """The config-off branch never inspects the client, so a non-loopback
    client is let through."""
    client = _stub_app(require_loopback_enabled=False, client=("10.0.0.4", 12345))
    response = client.get("/probe")
    assert response.status_code == 200


def test_require_loopback_allows_loopback_client():
    client = _stub_app(require_loopback_enabled=True, client=("127.0.0.1", 12345))
    response = client.get("/probe")
    assert response.status_code == 200


def test_require_loopback_refuses_non_loopback_client():
    client = _stub_app(require_loopback_enabled=True, client=("10.0.0.4", 12345))
    response = client.get("/probe")
    assert response.status_code == 403


def test_require_loopback_fails_closed_when_client_is_none():
    """`request.client` can be None (e.g. certain ASGI transports); with the
    guard enabled this must refuse, not silently allow."""
    client = _stub_app(require_loopback_enabled=True, client=None)
    response = client.get("/probe")
    assert response.status_code == 403
