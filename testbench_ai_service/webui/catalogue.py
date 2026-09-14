"""The model catalogue the console offers, derived rather than retyped.

**No model name is written in this module.** The built-in half comes from
``llm.routing.builtin_models_by_provider``, which reads the four frozensets the
clients dispatch on; the operator's half comes from
``llm_config.extra_models``. A hand-maintained constant here would be a third
list that goes stale independently of the two the service actually uses
(design D7).

Key presence goes through ``status.api_key_statuses`` so the
presence-never-values rule is enforced in one place (design 3.4).
"""

import os

from testbench_ai_service.config import AppConfig
from testbench_ai_service.llm.base import LLMProvider
from testbench_ai_service.llm.routing import builtin_models_by_provider
from testbench_ai_service.utils.naming import normalize_project_name
from testbench_ai_service.webui.models import (
    CatalogueModel,
    CatalogueProvider,
    ModelCatalogueResponse,
)
from testbench_ai_service.webui.status import api_key_statuses

#: The global credential each provider authenticates with. CUSTOM is None:
#: LLMFactory._get_api_key deliberately does not demand a 'CUSTOM_API_KEY',
#: so there is no variable whose absence would mean anything.
PROVIDER_KEY_NAMES: dict[LLMProvider, str | None] = {
    LLMProvider.OPENAI: "OPENAI_API_KEY",
    LLMProvider.ANTHROPIC: "ANTHROPIC_API_KEY",
    LLMProvider.AZURE_OPENAI: "AZURE_OPENAI_API_KEY",
    LLMProvider.CUSTOM: None,
}


def _key_present(config: AppConfig, provider: LLMProvider, project: str | None) -> bool:
    """Whether a run for this provider would find a credential at all.

    With a project, the project variable OR the global one counts -- which
    mirrors ``get_client``'s silent fallback (design 3.2) rather than
    contradicting it.
    """
    name = PROVIDER_KEY_NAMES[provider]
    if name is None:
        return True

    statuses = {status.name: status.present for status in api_key_statuses(config)}
    if statuses.get(name, False):
        return True

    if project is not None:
        scoped = f"{normalize_project_name(project)}_{name}"
        return bool(os.environ.get(scoped))
    return False


def build_catalogue(config: AppConfig, project: str | None = None) -> ModelCatalogueResponse:
    """Every model the console can offer, grouped by provider."""
    grouped = builtin_models_by_provider()

    entries: dict[LLMProvider, dict[str, CatalogueModel]] = {
        provider: {
            model: CatalogueModel(id=model, routing=family, source="builtin")
            for model, family in models.items()
        }
        for provider, models in grouped.items()
    }

    for name, extra in config.llm_config.extra_models.items():
        # setdefault, not assignment: LLMConfig refuses an entry that shadows a
        # built-in, so this can only ever add. Belt and braces -- a built-in
        # must never be displaceable by config.
        entries.setdefault(extra.provider, {}).setdefault(
            name, CatalogueModel(id=name, routing=extra.routing, source="config")
        )

    return ModelCatalogueResponse(
        providers=[
            CatalogueProvider(
                provider=provider,
                key_present=_key_present(config, provider, project),
                models=sorted(models.values(), key=lambda model: model.id),
            )
            for provider, models in entries.items()
        ]
    )
