import pytest

from testbench_ai_service.config import AppConfig
from testbench_ai_service.llm.base import LLMProvider, RoutingFamily
from testbench_ai_service.llm.routing import BUILTIN_ROUTING
from testbench_ai_service.models.config import LLMConfig
from testbench_ai_service.webui.catalogue import build_catalogue

TB_URL = "https://localhost:9443/api/"


@pytest.fixture(autouse=True)
def no_tb_probe(monkeypatch):
    monkeypatch.setattr("testbench_ai_service.config.validate_tb_server_url", lambda *a, **k: None)


def _config(**llm_kwargs) -> AppConfig:
    return AppConfig(tb_server_url=TB_URL, llm_config=LLMConfig(**llm_kwargs))


def _models(response, provider: LLMProvider) -> dict[str, RoutingFamily]:
    entry = next(p for p in response.providers if p.provider == provider)
    return {model.id: model.routing for model in entry.models}


class TestDerivation:
    def test_every_catalogue_entry_comes_from_a_routing_set(self):
        # The test that fails if anyone reintroduces a hand-maintained list.
        response = build_catalogue(_config())
        listed = {model.id for provider in response.providers for model in provider.models}
        assert listed == set(BUILTIN_ROUTING)

    def test_every_routing_set_member_is_listed(self):
        response = build_catalogue(_config())
        listed = {model.id for provider in response.providers for model in provider.models}
        for model in BUILTIN_ROUTING:
            assert model in listed

    def test_each_entry_reports_the_family_it_would_use(self):
        response = build_catalogue(_config())
        assert _models(response, LLMProvider.OPENAI)["gpt-4o"] is RoutingFamily.CHAT
        assert _models(response, LLMProvider.ANTHROPIC)["claude-haiku-4-5"] is RoutingFamily.BUDGET

    def test_builtins_are_marked_as_builtin(self):
        response = build_catalogue(_config())
        entry = next(p for p in response.providers if p.provider == LLMProvider.OPENAI)
        assert all(model.source == "builtin" for model in entry.models)

    def test_azure_and_custom_have_no_builtin_models(self):
        response = build_catalogue(_config())
        assert _models(response, LLMProvider.AZURE_OPENAI) == {}
        assert _models(response, LLMProvider.CUSTOM) == {}


class TestExtraModelsOverlay:
    def test_a_configured_model_appears_and_is_marked(self):
        config = _config(
            extra_models={"claude-opus-6": {"provider": "anthropic", "routing": "adaptive"}}
        )
        response = build_catalogue(config)
        entry = next(p for p in response.providers if p.provider == LLMProvider.ANTHROPIC)
        added = next(model for model in entry.models if model.id == "claude-opus-6")
        assert added.source == "config"
        assert added.routing is RoutingFamily.ADAPTIVE

    def test_a_configured_model_gives_azure_a_picker(self):
        config = _config(
            extra_models={"my-deployment": {"provider": "azure_openai", "routing": "chat"}}
        )
        response = build_catalogue(config)
        assert "my-deployment" in _models(response, LLMProvider.AZURE_OPENAI)

    def test_builtins_survive_the_overlay(self):
        config = _config(
            extra_models={"claude-opus-6": {"provider": "anthropic", "routing": "adaptive"}}
        )
        response = build_catalogue(config)
        assert "claude-haiku-4-5" in _models(response, LLMProvider.ANTHROPIC)


class TestKeyPresence:
    def test_reports_presence_for_the_provider_variable(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-global")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        response = build_catalogue(_config())
        by_provider = {p.provider: p.key_present for p in response.providers}
        assert by_provider[LLMProvider.ANTHROPIC] is True
        assert by_provider[LLMProvider.OPENAI] is False

    def test_never_returns_a_key_value(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-secret-value")
        response = build_catalogue(_config())
        assert "sk-secret-value" not in response.model_dump_json()

    def test_a_project_variable_counts_as_present(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setenv("CAR_CONFIGURATOR_OPENAI_API_KEY", "sk-project")
        response = build_catalogue(_config(), project="Car Configurator")
        by_provider = {p.provider: p.key_present for p in response.providers}
        assert by_provider[LLMProvider.OPENAI] is True

    def test_the_global_variable_still_counts_for_a_project(self, monkeypatch):
        # Mirrors get_client's silent fallback (design 3.2): the question the
        # operator is asking is "will a run find a key at all".
        monkeypatch.delenv("CAR_CONFIGURATOR_OPENAI_API_KEY", raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "sk-global")
        response = build_catalogue(_config(), project="Car Configurator")
        by_provider = {p.provider: p.key_present for p in response.providers}
        assert by_provider[LLMProvider.OPENAI] is True

    def test_custom_needs_no_key(self):
        response = build_catalogue(_config())
        by_provider = {p.provider: p.key_present for p in response.providers}
        assert by_provider[LLMProvider.CUSTOM] is True
