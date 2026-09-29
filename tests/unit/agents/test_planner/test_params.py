import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from testbench_ai_service.agents.test_planner.model import CutoffMode, ExistingMode
from testbench_ai_service.agents.test_planner.params import (
    VARIANT_MODES,
    UnknownVariantError,
    parse_run_params,
)
from testbench_ai_service.config import PROMPTS_DIR
from testbench_ai_service.models.config import PromptConfig
from testbench_ai_service.utils.prompt_utils import get_prompt_definition

LOCALES_DIR = Path(PROMPTS_DIR).parent / "locales"
LANGUAGES = ["de", "en"]


def _prompt_file(language):
    return PROMPTS_DIR / language / "test_planner" / "prompt.yaml"


def _config(language="de", variant=None, variables=None):
    return PromptConfig(file=_prompt_file(language), variant=variant, vars=variables)


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_variant_maps_to_a_mode_and_has_only_optional_vars(language):
    definition = get_prompt_definition(_prompt_file(language))

    assert definition.default_variant in {v.name for v in definition.variants}
    assert {VARIANT_MODES[v.name] for v in definition.variants} == set(CutoffMode)
    for variant in definition.variants:
        assert variant.messages == []
        for var in variant.vars.values():
            assert not var.required
            assert var.default_value is not None


def test_default_variant_is_auto_with_keep():
    params = parse_run_params(_config())

    assert params.mode == CutoffMode.AUTO
    assert params.existing == ExistingMode.KEEP


@pytest.mark.parametrize(
    ("language", "variant", "field", "default"),
    [
        ("de", "Anzahl", "count", 40),
        ("de", "Zeitbudget", "budget_minutes", 240),
        ("de", "Requirement-Abdeckung", "coverage_percent", 100),
        ("en", "Count", "count", 40),
        ("en", "Time budget", "budget_minutes", 240),
        ("en", "Requirement coverage", "coverage_percent", 100),
    ],
)
def test_variant_defaults(language, variant, field, default):
    assert getattr(parse_run_params(_config(language, variant)), field) == default


def test_request_vars_override_defaults():
    params = parse_run_params(
        _config(variant="Anzahl", variables={"count": "12", "existing": "replan"})
    )

    assert params.count == 12
    assert params.existing == ExistingMode.REPLAN


def test_empty_string_var_falls_back_to_default():
    assert parse_run_params(_config(variant="Anzahl", variables={"count": ""})).count == 40


def test_vars_of_other_variants_are_ignored():
    params = parse_run_params(_config(variant="Anzahl", variables={"budget_minutes": "5"}))

    assert params.budget_minutes is None


def test_invalid_value_raises_validation_error():
    with pytest.raises(ValidationError):
        parse_run_params(_config(variant="Anzahl", variables={"count": "-3"}))


def test_unknown_variant():
    with pytest.raises(UnknownVariantError) as exc:
        parse_run_params(_config(variant="Nope"))

    assert exc.value.variant == "Nope"


@pytest.mark.parametrize("language", LANGUAGES)
def test_locale_keys_exist(language):
    messages = json.loads((LOCALES_DIR / f"{language}.json").read_text(encoding="utf-8"))

    for key in [
        "test_planner.precheck.unsupported_tov_format",
        "test_planner.precheck.unknown_variant",
        "test_planner.precheck.invalid_vars",
        "test_planner.precheck.too_few_test_cases",
        "test_planner.precheck.missing_requirement_links",
        "test_planner.precheck.missing_durations",
        "test_planner.run.seeds_exceed_count",
        "test_planner.run.seeds_exceed_budget",
        "test_planner.run.no_requirements_fallback",
    ]:
        assert key in messages
