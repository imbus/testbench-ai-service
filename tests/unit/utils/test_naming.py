import pytest

from testbench_ai_service.utils.naming import normalize_project_name


@pytest.mark.parametrize(
    ("project_name", "expected"),
    [
        ("Car Configurator", "CAR_CONFIGURATOR"),
        ("my-project", "MY_PROJECT"),
        ("Projekt (2026)", "PROJEKT_2026_"),
        ("already_normalized", "ALREADY_NORMALIZED"),
    ],
)
def test_normalize_project_name(project_name, expected):
    assert normalize_project_name(project_name) == expected


def test_matches_factory_helper():
    """The factory helper must stay in lockstep with the shared function."""
    from testbench_ai_service.llm.factory import LLMFactory

    factory = LLMFactory()
    assert factory._normalize_project_name("Car Configurator") == normalize_project_name(
        "Car Configurator"
    )
