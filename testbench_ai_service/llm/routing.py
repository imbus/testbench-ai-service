"""The models each client knows how to call, as one derived table.

**This module writes down no model names.** It reads the four frozensets the
clients already dispatch on, so "which models exist" and "which models route
properly" cannot drift apart (design D7). Adding a model to a client's set is
the single act that both routes it and lists it.

Import direction is one-way: this module imports the clients, never the other
way round. A client that needs to name a family imports ``RoutingFamily`` from
``llm.base``, which imports nothing of ours.
"""

from testbench_ai_service.llm.anthropic import (
    ADAPTIVE_THINKING_MODELS,
    BUDGET_THINKING_MODELS,
)
from testbench_ai_service.llm.base import LLMProvider, RoutingFamily
from testbench_ai_service.llm.openai import CHAT_MODELS, REASONING_MODELS

#: Every built-in model, mapped to the branch its client would take.
BUILTIN_ROUTING: dict[str, RoutingFamily] = {
    **dict.fromkeys(CHAT_MODELS, RoutingFamily.CHAT),
    **dict.fromkeys(REASONING_MODELS, RoutingFamily.REASONING),
    **dict.fromkeys(BUDGET_THINKING_MODELS, RoutingFamily.BUDGET),
    **dict.fromkeys(ADAPTIVE_THINKING_MODELS, RoutingFamily.ADAPTIVE),
}


def builtin_routing(model: str) -> RoutingFamily | None:
    """The family *model* routes to, or None when no client claims it."""
    return BUILTIN_ROUTING.get(model)


def builtin_models_by_provider() -> dict[LLMProvider, dict[str, RoutingFamily]]:
    """The built-in catalogue, grouped by the provider that serves it.

    Azure OpenAI and CUSTOM are present and empty rather than absent: both are
    real providers whose model list is per-installation (design 3.9), and a
    caller iterating this map should see them as "nothing built in" rather
    than have to know they were skipped.
    """
    return {
        LLMProvider.OPENAI: {
            **dict.fromkeys(CHAT_MODELS, RoutingFamily.CHAT),
            **dict.fromkeys(REASONING_MODELS, RoutingFamily.REASONING),
        },
        LLMProvider.ANTHROPIC: {
            **dict.fromkeys(BUDGET_THINKING_MODELS, RoutingFamily.BUDGET),
            **dict.fromkeys(ADAPTIVE_THINKING_MODELS, RoutingFamily.ADAPTIVE),
        },
        LLMProvider.AZURE_OPENAI: {},
        LLMProvider.CUSTOM: {},
    }
