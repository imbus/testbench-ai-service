from pathlib import Path

import pytest
from fastapi import HTTPException

from testbench_ai_service.webui.config_io import CONFIG_PREFIX, read_config_file

SAMPLE = """
[testbench-ai-service]
# A comment an operator wrote and expects to keep
tb_server_url = "https://tb.example.com:9443/api/"
port = 9999
language = "en"

[testbench-ai-service.llm_config]
provider = "anthropic"
"""


def test_reads_the_prefixed_section(tmp_path: Path):
    assert CONFIG_PREFIX in SAMPLE
    path = tmp_path / "config.toml"
    path.write_text(SAMPLE, encoding="utf-8")
    data = read_config_file(path)
    assert data["port"] == 9999
    assert data["llm_config"]["provider"] == "anthropic"


def test_missing_file_yields_empty_dict(tmp_path: Path):
    assert read_config_file(tmp_path / "absent.toml") == {}


def test_malformed_toml_raises_a_400(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text("this is [not valid toml", encoding="utf-8")
    with pytest.raises(HTTPException) as exc:
        read_config_file(path)
    assert exc.value.status_code == 400
    assert str(path) in str(exc.value.detail)


def test_endpoint_requires_a_session(client):
    assert client.get("/admin/api/config").status_code == 401


def test_endpoint_returns_running_config(client, login):
    login()
    body = client.get("/admin/api/config").json()
    assert body["running"]["port"] == 8010
    assert body["running"]["llm_config"]["provider"] == "openai"
    assert "test_case_set_reviewer" in body["running"]["agents"]


def test_endpoint_never_leaks_the_loaded_from_path_field(client, login):
    """`loaded_from` is excluded from the model dump; the path is reported once,
    explicitly, as config_path."""
    login()
    body = client.get("/admin/api/config").json()
    assert "loaded_from" not in body["running"]
    assert body["running"]["port"] == 8010
    assert body["config_path"]


def test_non_admin_may_read_config(client, login):
    """Phase 1 is read-only for everyone; only writes need admin."""
    login(roles=["ProjectUser"])
    assert client.get("/admin/api/config").status_code == 200
