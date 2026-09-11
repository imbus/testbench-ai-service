import pytest

from testbench_ai_service.webui.prompt_refs import variant_references


def test_finds_the_global_agents_reference():
    disk = {"agents": {"defect_explainer": {"prompt": {"variant": "Detailed"}}}}
    refs = variant_references("defect_explainer", disk)
    assert [(r.agent, r.project, r.variant) for r in refs] == [
        ("defect_explainer", None, "Detailed")
    ]


def test_finds_a_project_override_reference():
    """models/config.py:84 -- ProjectPromptConfig.variant is a second free string."""
    disk = {
        "projects": {"Alpha": {"agents": {"defect_explainer": {"prompt": {"variant": "Short"}}}}}
    }
    refs = variant_references("defect_explainer", disk)
    assert [(r.agent, r.project, r.variant) for r in refs] == [
        ("defect_explainer", "Alpha", "Short")
    ]


def test_finds_both_at_once():
    disk = {
        "agents": {"a": {"prompt": {"variant": "G"}}},
        "projects": {"P": {"agents": {"a": {"prompt": {"variant": "P1"}}}}},
    }
    assert {(r.project, r.variant) for r in variant_references("a", disk)} == {
        (None, "G"),
        ("P", "P1"),
    }


def test_ignores_other_agents():
    disk = {"agents": {"other": {"prompt": {"variant": "X"}}}}
    assert variant_references("a", disk) == []


def test_an_agent_with_no_variant_key_contributes_nothing():
    disk = {"agents": {"a": {"prompt": {"file": "p.yaml"}}}}
    assert variant_references("a", disk) == []


@pytest.mark.parametrize(
    "disk",
    [
        {"agents": "not-a-table"},
        {"agents": {"a": "not-a-table"}},
        {"agents": {"a": {"prompt": "not-a-table"}}},
        {"agents": {"a": {"prompt": {"variant": 17}}}},
        {"projects": "not-a-table"},
        {"projects": {"P": {"agents": {"a": {"prompt": {"variant": None}}}}}},
        {},
    ],
)
def test_unvalidated_toml_shapes_cost_a_check_not_a_crash(disk):
    """`disk` is raw TOML. A bad shape must not raise."""
    assert variant_references("a", disk) == []
