"""Tests for rendering the context sent to the model."""

from testbench_ai_service.agents.requirement.context import (
    assemble_context,
    render_existing_tests,
    render_requirement,
)
from testbench_ai_service.agents.requirement.model import ExtendedRequirement, ThemeContext
from testbench_ai_service.models.testbench import RequirementAssignment


def _requirement(extended_id: str = "ER_1", **overrides: str) -> ExtendedRequirement:
    fields = {
        "key": "473",
        "name": "Automatic discount",
        "id": extended_id,
        "extendedId": extended_id,
        "version": "1",
        "owner": "someone",
        "status": "open",
        "priority": "high",
        "repositoryId": "MS Excel",
    }
    return ExtendedRequirement.from_assignment(RequirementAssignment(**(fields | overrides)))


class TestRenderRequirement:
    def test_renders_identifier_title_and_attributes(self):
        assert render_requirement(_requirement()) == (
            "- ER_1: Automatic discount\n"
            "  version: 1 | status: open | priority: high | owner: someone"
        )

    def test_omits_empty_attributes(self):
        rendered = render_requirement(_requirement(owner="", priority=""))

        assert rendered.splitlines()[1] == "  version: 1 | status: open"

    def test_renders_description_indented_below_attributes(self):
        requirement = _requirement().model_copy(
            update={"description": "Orders above 100 EUR\nget 5 % off."}
        )

        assert render_requirement(requirement).splitlines()[2:] == [
            "  description:",
            "    Orders above 100 EUR",
            "    get 5 % off.",
        ]

    def test_omits_description_without_visible_text(self):
        requirement = _requirement().model_copy(update={"description": "<p> </p>"})

        assert len(render_requirement(requirement).splitlines()) == 2


class TestRenderExistingTests:
    def test_lists_description_and_test_case_sets(self):
        rendered = render_existing_tests(
            ThemeContext(theme_name="Discounts", description="Old", test_case_sets=["TCS 1"])
        )

        assert rendered == (
            "Test theme: Discounts\n"
            "Current description: Old\n"
            "Test case sets already below this theme:\n"
            "- TCS 1"
        )

    def test_leaves_out_a_blank_description(self):
        rendered = render_existing_tests(ThemeContext(theme_name="Discounts", description=" "))

        assert rendered == "Test theme: Discounts"


def test_assemble_context_renders_one_entry_per_target_in_order():
    agent_data = assemble_context(
        targets=[_requirement("ER_1"), _requirement("ER_2")],
        theme_context=ThemeContext(theme_name="Discounts"),
    )

    assert [entry.splitlines()[0] for entry in agent_data["requirements"]] == [
        "- ER_1: Automatic discount",
        "- ER_2: Automatic discount",
    ]
    assert agent_data["existing_tests"] == "Test theme: Discounts"
