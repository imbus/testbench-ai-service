from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from testbench_ai_service.webui.static import mount_spa


@pytest.fixture
def spa_dir(tmp_path: Path) -> Path:
    (tmp_path / "index.html").write_text("<!doctype html>SPA ROOT", encoding="utf-8")
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "app.js").write_text("console.log(1)", encoding="utf-8")
    return tmp_path


@pytest.fixture
def client(spa_dir: Path) -> TestClient:
    app = FastAPI()
    mount_spa(app, spa_dir, "/admin")
    return TestClient(app)


def test_serves_index_at_mount_root(client: TestClient):
    response = client.get("/admin/")
    assert response.status_code == 200
    assert "SPA ROOT" in response.text


def test_serves_real_assets(client: TestClient):
    response = client.get("/admin/assets/app.js")
    assert response.status_code == 200
    assert response.text == "console.log(1)"


def test_client_route_falls_back_to_index(client: TestClient):
    """A deep link must survive a page reload."""
    response = client.get("/admin/prompts/de/test_case_set_reviewer")
    assert response.status_code == 200
    assert "SPA ROOT" in response.text


def test_missing_asset_is_404_not_index(client: TestClient):
    """Serving index.html for a missing .js would surface as a syntax error
    in the browser instead of an honest 404."""
    response = client.get("/admin/assets/missing.js")
    assert response.status_code == 404


def test_missing_directory_serves_placeholder(tmp_path: Path):
    """A pip install without a frontend build must not crash at startup."""
    app = FastAPI()
    mount_spa(app, tmp_path / "does-not-exist", "/admin")
    response = TestClient(app).get("/admin/")
    assert response.status_code == 200
    assert "not been built" in response.text
