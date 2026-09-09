from pathlib import Path

import pytest
from fastapi import HTTPException

from testbench_ai_service.llm.base import LLMProvider
from testbench_ai_service.models.config import LLMConfig, ProjectConfig
from testbench_ai_service.webui.config_io import (
    CONFIG_PREFIX,
    build_config_response,
    read_config_file,
    redact_credentials,
    redact_toml_text,
)

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


def test_undecodable_bytes_raise_a_400(tmp_path: Path):
    """Not every broken file is invalid TOML syntax -- binary garbage fails at
    the UTF-8 decode step inside tomllib.load, before TOML parsing even starts.
    That must surface the same 400-naming-the-file shape, not a 500."""
    path = tmp_path / "config.toml"
    path.write_bytes(b"\xff\xfe\x00\x01 not valid utf-8 \xfa")
    with pytest.raises(HTTPException) as exc:
        read_config_file(path)
    assert exc.value.status_code == 400
    assert str(path) in str(exc.value.detail)


DISK_WITH_PLANTED_SECRETS = """
[testbench-ai-service]
port = 9999

[testbench-ai-service.llm_config]
provider = "anthropic"
api_key = "sk-disk-secret"

[testbench-ai-service.projects.proj1.llm_config]
provider = "openai"
api_key = "sk-disk-nested-secret"
"""


def test_redacts_a_planted_api_key_in_running_and_disk(tmp_path: Path, make_app):
    """An operator's mistaken `api_key = "..."` under `[llm_config]` must not
    round-trip through either half of the payload -- `disk` is raw file content
    with no model to protect it, and `running` picked up the same extra field
    because `LLMConfig` allows it."""
    disk_path = tmp_path / "config.toml"
    disk_path.write_text(DISK_WITH_PLANTED_SECRETS, encoding="utf-8")

    app = make_app(llm_config={"provider": "openai", "api_key": "sk-running-secret"})
    response = build_config_response(app.state.config, disk_path)

    assert response.running["llm_config"]["api_key"] == "***REDACTED***"
    assert response.disk["llm_config"]["api_key"] == "***REDACTED***"
    assert "sk-running-secret" not in str(response.running)
    assert "sk-disk-secret" not in str(response.disk)


def test_redacts_a_planted_api_key_in_nested_project_llm_config(tmp_path: Path, make_app):
    """`llm_config` also appears nested under `projects.<name>.llm_config`; the
    redaction must recurse rather than only inspect the top level."""
    disk_path = tmp_path / "config.toml"
    disk_path.write_text(DISK_WITH_PLANTED_SECRETS, encoding="utf-8")

    app = make_app(
        projects={
            "proj1": ProjectConfig(
                llm_config=LLMConfig(provider=LLMProvider.OPENAI, api_key="sk-nested-secret")
            )
        }
    )
    response = build_config_response(app.state.config, disk_path)

    assert response.running["projects"]["proj1"]["llm_config"]["api_key"] == "***REDACTED***"
    assert response.disk["projects"]["proj1"]["llm_config"]["api_key"] == "***REDACTED***"
    assert "sk-nested-secret" not in str(response.running)
    assert "sk-disk-nested-secret" not in str(response.disk)


def test_ssl_key_is_not_redacted(tmp_path: Path, make_app):
    """`ssl_key` is a filesystem path to a certificate key file, not a secret
    value -- a bare 'key' substring match would wrongly catch it."""
    key_file = tmp_path / "server.key"
    key_file.write_text("not a real key, just a path target", encoding="utf-8")
    app = make_app(ssl_key=str(key_file))

    response = build_config_response(app.state.config, tmp_path / "absent.toml")

    assert response.running["ssl_key"] == str(key_file)


def test_api_version_is_not_redacted(make_app):
    """`api_version` contains the substring 'api' but is not a credential; only
    the compound tokens 'api_key'/'apikey' should match."""
    app = make_app(
        llm_config={
            "provider": "azure_openai",
            "azure_endpoint": "https://example.openai.azure.com",
            "api_version": "2024-02-01",
        }
    )

    response = build_config_response(app.state.config, Path("absent.toml"))

    assert response.running["llm_config"]["api_version"] == "2024-02-01"


def test_auth_method_value_of_api_key_is_not_redacted(app):
    """`auth_method`'s legitimate value is the literal string 'api_key' (from
    `AzureAuthMethod.API_KEY`); redaction matches key NAMES, never values."""
    response = build_config_response(app.state.config, Path("absent.toml"))

    assert response.running["llm_config"]["auth_method"] == "api_key"


@pytest.mark.parametrize("key", ["api-key", "x-api-key", "api.key", "API-KEY"])
def test_hyphenated_and_dotted_credential_keys_are_redacted(key: str):
    """Separator variants of the compound 'api_key' token must match too --
    `redact_credentials` previously matched key names by bare substring only,
    so `{"api-key": "..."}` round-tripped a real secret through `GET /config`
    unredacted. Separators are folded to '_' before matching, so 'api-key',
    'x-api-key', 'api.key' and a differently-cased 'API-KEY' all match
    exactly as 'api_key' does."""
    redacted = redact_credentials({"llm_config": {key: "sk-hyphen-secret"}})

    assert redacted["llm_config"][key] == "***REDACTED***"


def test_ssl_key_dict_key_is_not_redacted_by_redact_credentials():
    """Regression guard for the deliberate exclusion: separator normalisation
    must not turn the bare 'key' substring into a match. 'ssl_key' has no
    '-', '.' or ' ' to normalise and still must not match, exactly as before."""
    redacted = redact_credentials({"ssl_key": "/etc/certs/key.pem"})

    assert redacted["ssl_key"] == "/etc/certs/key.pem"


def test_auth_method_dict_key_is_not_redacted_by_redact_credentials():
    """Regression guard: 'auth_method' must still not match after separator
    normalisation was added -- it contains none of '-', '.' or ' ' either."""
    redacted = redact_credentials({"auth_method": "api_key"})

    assert redacted["auth_method"] == "api_key"


AOT_WITH_SECRETS = """\
[testbench-ai-service]
port = 8010

[[tool.other.entries]]
api_key = "sk-IN-AOT"
name = "one"

[[tool.other.entries]]
api_key = "sk-IN-AOT-2"
"""


def test_redact_toml_text_redacts_a_credential_inside_an_array_of_tables():
    """`config.toml` is a potentially shared file (`load_config_from_file`
    falls back to `pyproject.toml`), so a credential planted in another
    tool's `[[array.of.tables]]` section is a realistic shape, not only a
    scalar table. Both entries must be redacted, not just the first."""
    out = redact_toml_text(AOT_WITH_SECRETS)

    assert "sk-IN-AOT" not in out
    assert "sk-IN-AOT-2" not in out
    assert out.count("***REDACTED***") == 2


def test_redact_toml_text_still_redacts_an_array_valued_credential():
    """An array-VALUED credential key (`api_keys = ["sk-A", "sk-B"]`) is not
    an array of TABLES -- it is a plain list value under a credential-named
    key -- and must still be replaced whole by the sentinel, exactly as
    before this fix."""
    out = redact_toml_text('[x]\napi_keys = ["sk-A", "sk-B"]\n')

    assert "sk-A" not in out
    assert "sk-B" not in out
    assert 'api_keys = "***REDACTED***"' in out
