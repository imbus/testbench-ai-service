import pytest
from pydantic import ValidationError

from testbench_ai_service.llm.base import LLMProvider, RoutingFamily
from testbench_ai_service.models.config import ExtraModel, LLMConfig


def test_timeout_zero_rejected():
    with pytest.raises(ValidationError):
        LLMConfig(provider=LLMProvider.OPENAI, timeout=0)


def test_timeout_negative_rejected():
    with pytest.raises(ValidationError):
        LLMConfig(provider=LLMProvider.OPENAI, timeout=-1)


def test_timeout_positive_accepted():
    config = LLMConfig(provider=LLMProvider.OPENAI, timeout=0.5)
    assert config.timeout == 0.5


def test_max_retries_negative_rejected():
    with pytest.raises(ValidationError):
        LLMConfig(provider=LLMProvider.OPENAI, max_retries=-1)


def test_max_retries_zero_accepted():
    config = LLMConfig(provider=LLMProvider.OPENAI, max_retries=0)
    assert config.max_retries == 0


def test_timeout_and_max_retries_default_to_none():
    config = LLMConfig(provider=LLMProvider.OPENAI)
    assert config.timeout is None
    assert config.max_retries is None


class TestExtraModels:
    def test_defaults_to_empty(self):
        assert LLMConfig().extra_models == {}

    def test_accepts_a_valid_anthropic_entry(self):
        config = LLMConfig(
            extra_models={"claude-opus-6": {"provider": "anthropic", "routing": "adaptive"}}
        )
        entry = config.extra_models["claude-opus-6"]
        assert entry.provider is LLMProvider.ANTHROPIC
        assert entry.routing is RoutingFamily.ADAPTIVE

    def test_accepts_a_valid_openai_entry(self):
        config = LLMConfig(extra_models={"gpt-6": {"provider": "openai", "routing": "reasoning"}})
        assert config.extra_models["gpt-6"].routing is RoutingFamily.REASONING

    @pytest.mark.parametrize(
        ("provider", "routing"),
        [
            ("anthropic", "chat"),
            ("anthropic", "reasoning"),
            ("openai", "adaptive"),
            ("openai", "budget"),
            ("azure_openai", "budget"),
            ("custom", "chat"),
            ("custom", "adaptive"),
        ],
    )
    def test_refuses_a_routing_family_the_provider_cannot_use(self, provider, routing):
        with pytest.raises(ValidationError) as excinfo:
            LLMConfig(extra_models={"m": {"provider": provider, "routing": routing}})
        assert "extra_models" in str(excinfo.value)

    @pytest.mark.parametrize(
        ("provider", "routing"),
        [
            ("anthropic", "fallback"),
            ("openai", "fallback"),
            ("azure_openai", "chat"),
            ("azure_openai", "reasoning"),
            ("custom", "fallback"),
        ],
    )
    def test_allows_every_family_its_provider_can_use(self, provider, routing):
        config = LLMConfig(extra_models={"m": {"provider": provider, "routing": routing}})
        assert config.extra_models["m"].routing is RoutingFamily(routing)

    def test_refuses_an_entry_that_shadows_a_builtin(self):
        # gpt-4o is in CHAT_MODELS; letting config redefine it would let a typo
        # silently change how a shipped model is called (design 6, 9).
        with pytest.raises(ValidationError) as excinfo:
            LLMConfig(extra_models={"gpt-4o": {"provider": "openai", "routing": "reasoning"}})
        assert "gpt-4o" in str(excinfo.value)

    def test_the_error_path_names_the_offending_field(self):
        # ConfigSection renders issues against the field they name, so the path
        # has to reach the row (design 5.3).
        with pytest.raises(ValidationError) as excinfo:
            LLMConfig(extra_models={"m": {"provider": "anthropic", "routing": "chat"}})
        assert "extra_models" in str(excinfo.value)


class TestExtraModelStandalone:
    def test_requires_both_fields(self):
        with pytest.raises(ValidationError):
            ExtraModel(provider="openai")
