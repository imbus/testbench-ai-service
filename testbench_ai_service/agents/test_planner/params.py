"""Turns the prompt variant and its vars into the run parameters."""

from testbench_ai_service.agents.test_planner.model import CutoffMode, PlannerRunParams
from testbench_ai_service.models.config import PromptConfig
from testbench_ai_service.utils.prompt_utils import get_prompt_definition, get_prompt_variant

#: The variant names of both languages and the cut-off mode they stand for.
VARIANT_MODES: dict[str, CutoffMode] = {
    "Automatisch": CutoffMode.AUTO,
    "Automatic": CutoffMode.AUTO,
    "Anzahl": CutoffMode.COUNT,
    "Count": CutoffMode.COUNT,
    "Zeitbudget": CutoffMode.BUDGET,
    "Time budget": CutoffMode.BUDGET,
    "Requirement-Abdeckung": CutoffMode.COVERAGE,
    "Requirement coverage": CutoffMode.COVERAGE,
}


class UnknownVariantError(ValueError):
    def __init__(self, variant: str):
        super().__init__(f"Unknown test planner variant '{variant}'")
        self.variant = variant


def parse_run_params(prompt_config: PromptConfig) -> PlannerRunParams:
    """
    Read the cut-off mode from the variant and the values from its vars.

    Vars the variant does not declare are ignored; empty values count as unset,
    so the default of the variant applies.

    Raises:
        UnknownVariantError: If the variant does not exist or maps to no mode.
        pydantic.ValidationError: If a value is invalid.
    """
    definition = get_prompt_definition(prompt_config.file)
    try:
        variant = get_prompt_variant(definition, prompt_config.variant)
    except ValueError as e:
        raise UnknownVariantError(prompt_config.variant or "") from e
    mode = VARIANT_MODES.get(variant.name)
    if mode is None:
        raise UnknownVariantError(variant.name)

    values = {
        name: definition_.default_value
        for name, definition_ in variant.vars.items()
        if definition_.default_value is not None
    }
    values.update(
        {
            name: value
            for name, value in (prompt_config.vars or {}).items()
            if name in variant.vars and value != ""
        }
    )
    return PlannerRunParams(mode=mode, **values)
