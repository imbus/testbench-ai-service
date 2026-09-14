from testbench_ai_service.llm.anthropic import (
    ADAPTIVE_THINKING_MODELS,
    BUDGET_THINKING_MODELS,
)
from testbench_ai_service.llm.base import LLMProvider, RoutingFamily
from testbench_ai_service.llm.openai import CHAT_MODELS, REASONING_MODELS
from testbench_ai_service.llm.routing import (
    BUILTIN_ROUTING,
    builtin_models_by_provider,
    builtin_routing,
)


class TestBuiltinRouting:
    def test_every_set_member_is_mapped(self):
        expected = (
            CHAT_MODELS | REASONING_MODELS | BUDGET_THINKING_MODELS | ADAPTIVE_THINKING_MODELS
        )
        assert set(BUILTIN_ROUTING) == expected

    def test_each_set_maps_to_its_own_family(self):
        assert BUILTIN_ROUTING["gpt-4o"] is RoutingFamily.CHAT
        assert BUILTIN_ROUTING["o3"] is RoutingFamily.REASONING
        assert BUILTIN_ROUTING["claude-haiku-4-5"] is RoutingFamily.BUDGET
        assert BUILTIN_ROUTING["claude-opus-4-6"] is RoutingFamily.ADAPTIVE

    def test_an_unknown_model_is_not_mapped(self):
        assert builtin_routing("no-such-model-9000") is None

    def test_lookup_matches_the_table(self):
        assert builtin_routing("gpt-4o") is RoutingFamily.CHAT


class TestBuiltinModelsByProvider:
    def test_openai_sets_land_under_openai(self):
        by_provider = builtin_models_by_provider()
        assert set(by_provider[LLMProvider.OPENAI]) == CHAT_MODELS | REASONING_MODELS

    def test_anthropic_sets_land_under_anthropic(self):
        by_provider = builtin_models_by_provider()
        expected = BUDGET_THINKING_MODELS | ADAPTIVE_THINKING_MODELS
        assert expected == set(by_provider[LLMProvider.ANTHROPIC])

    def test_azure_and_custom_contribute_nothing(self):
        # Design 3.9: Azure dispatches on the canonical name after
        # deployment_mapping, which is per-installation data; CUSTOM loads an
        # arbitrary class. Neither can be enumerated here.
        by_provider = builtin_models_by_provider()
        assert by_provider[LLMProvider.AZURE_OPENAI] == {}
        assert by_provider[LLMProvider.CUSTOM] == {}
