from unittest.mock import patch

import pytest

from testbench_ai_service.llm.base import AzureAuthMethod, LLMProvider
from testbench_ai_service.llm.credentials import (
    get_api_key,
    get_project_api_key,
    resolve_credential,
    uses_entra_id,
)
from testbench_ai_service.models.config import LLMConfig

AZURE_ENTRA = LLMConfig(
    provider=LLMProvider.AZURE_OPENAI,
    auth_method=AzureAuthMethod.ENTRA_ID,
    azure_endpoint="https://x.openai.azure.com",
    api_version="2024-10-21",
)


def test_global_api_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k")

    assert get_api_key(LLMProvider.OPENAI) == "k"


def test_missing_global_api_key_raises(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(ValueError, match="not found"):
        get_api_key(LLMProvider.OPENAI)


def test_custom_provider_needs_no_key():
    assert get_api_key(LLMProvider.CUSTOM) is None


def test_project_api_key(monkeypatch):
    monkeypatch.setenv("CAR_CONFIGURATOR_OPENAI_API_KEY", "p")

    assert get_project_api_key("Car Configurator", LLMProvider.OPENAI) == "p"


def test_uses_entra_id_only_for_azure():
    assert uses_entra_id(LLMProvider.AZURE_OPENAI, AZURE_ENTRA)
    assert not uses_entra_id(LLMProvider.OPENAI, AZURE_ENTRA)


def test_resolve_prefers_project_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "global")
    monkeypatch.setenv("P_OPENAI_API_KEY", "project")

    assert resolve_credential(LLMProvider.OPENAI, LLMConfig(), "P") == "project"


def test_resolve_falls_back_to_global_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "global")
    monkeypatch.delenv("P_OPENAI_API_KEY", raising=False)

    assert resolve_credential(LLMProvider.OPENAI, LLMConfig(), "P") == "global"


def test_resolve_entra_id_project_then_global():
    with patch(
        "testbench_ai_service.llm.credentials.resolve_entra_credentials",
        side_effect=[None, "global-entra"],
    ) as resolve:
        assert resolve_credential(LLMProvider.AZURE_OPENAI, AZURE_ENTRA, "P") == "global-entra"

    assert [call.args for call in resolve.call_args_list] == [("P",), (None,)]
