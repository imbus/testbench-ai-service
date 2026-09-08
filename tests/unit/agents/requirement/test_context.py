"""Tests for the tiered, budget-trimmed context assembler."""

from testbench_ai_service.agents.requirement.context import TokenBudget, assemble_context
from testbench_ai_service.agents.requirement.model import ThemeContext
from testbench_ai_service.agents.requirement.ranking import LexicalRanker
from testbench_ai_service.agents.requirement.tree import find_requirement


def _target(baseline, extended_id="ER_WHY299"):
    found = find_requirement(baseline.children, extended_id)
    assert found is not None
    return found


def _theme(description="Existing theme description", test_case_sets=("Discount TCS",)):
    return ThemeContext(
        theme_name="Discounts",
        description=description,
        test_case_sets=list(test_case_sets),
        related_tests={"ER_WHY298": ["Allow discount TCS"]},
    )


async def _assemble(baseline, target, theme=None, budget=None):
    return await assemble_context(
        baseline=baseline,
        target=target,
        theme_context=theme,
        ranker=LexicalRanker(),
        budget=budget or TokenBudget(),
    )


class TestStructuralCore:
    async def test_renders_the_target_in_full_detail(self, baseline):
        data = await _assemble(baseline, _target(baseline))

        assert "ER_WHY299: Automatic discount" in data["requirement"]
        assert "Business Units: Marketing" in data["requirement"]

    async def test_renders_the_ancestor_chain_outermost_first(self, baseline):
        data = await _assemble(baseline, _target(baseline))

        lines = data["requirement_path"].splitlines()
        assert "EF_3100077" in lines[0]
        assert "ER_WHY298" in lines[1]

    async def test_renders_siblings(self, baseline):
        data = await _assemble(baseline, _target(baseline))

        assert "ER_WHY300" in data["requirement_siblings"]
        assert "ER_WHY299" not in data["requirement_siblings"]

    async def test_renders_the_subtree_indented_by_depth(self, baseline):
        data = await _assemble(baseline, _target(baseline, "EF_3100077"))

        lines = data["requirement_subtree"].splitlines()
        assert lines[0].startswith("- ER_WHY297")
        assert any(line.startswith("  - ER_WHY299") for line in lines)

    async def test_renders_empty_sections_rather_than_omitting_them(self, baseline):
        data = await _assemble(baseline, _target(baseline, "ER_DSGN309"))

        assert data["requirement_subtree"] == ""
        assert data["existing_tests"] == ""
        assert data["related_tests"] == ""

    async def test_passes_the_target_model_through_for_template_use(self, baseline):
        target = _target(baseline)

        data = await _assemble(baseline, target)

        assert data["requirement_obj"] is target


class TestThemeTiers:
    async def test_renders_the_theme_description_and_its_test_case_sets(self, baseline):
        data = await _assemble(baseline, _target(baseline), theme=_theme())

        assert "Existing theme description" in data["existing_tests"]
        assert "Discount TCS" in data["existing_tests"]

    async def test_renders_tests_linked_to_nearby_requirements(self, baseline):
        data = await _assemble(baseline, _target(baseline), theme=_theme())

        assert "ER_WHY298" in data["related_tests"]
        assert "Allow discount TCS" in data["related_tests"]


class TestRelatedRequirements:
    async def test_fills_the_tier_from_the_ranker(self, baseline):
        data = await _assemble(baseline, _target(baseline))

        assert "ER_WHY300" in data["related_requirements"]

    async def test_never_truncates_a_line_part_way_through(self, baseline, make_requirement):
        baseline.children.extend(
            make_requirement(f"BULK{index:03d}", "Automatic discount variant")
            for index in range(200)
        )

        data = await _assemble(
            baseline,
            _target(baseline),
            budget=TokenBudget(related_requirements=40),
        )

        for line in data["related_requirements"].splitlines():
            assert line.startswith("- ")
            assert ": " in line

    async def test_stops_adding_entries_once_the_tier_cap_is_spent(
        self, baseline, make_requirement
    ):
        baseline.children.extend(
            make_requirement(f"BULK{index:03d}", "Automatic discount variant")
            for index in range(200)
        )

        generous = await _assemble(
            baseline, _target(baseline), budget=TokenBudget(related_requirements=4000)
        )
        tight = await _assemble(
            baseline, _target(baseline), budget=TokenBudget(related_requirements=40)
        )

        assert (
            0
            < len(tight["related_requirements"].splitlines())
            < len(generous["related_requirements"].splitlines())
        )

    async def test_is_empty_when_not_even_one_entry_fits(self, baseline, make_requirement):
        baseline.children.extend(
            make_requirement(f"BULK{index:03d}", "Automatic discount variant")
            for index in range(20)
        )

        data = await _assemble(
            baseline, _target(baseline), budget=TokenBudget(related_requirements=1)
        )

        assert data["related_requirements"] == ""

    async def test_cannot_starve_the_theme_tiers(self, baseline, make_requirement):
        baseline.children.extend(
            make_requirement(f"BULK{index:03d}", "Automatic discount variant")
            for index in range(500)
        )

        data = await _assemble(
            baseline,
            _target(baseline),
            theme=_theme(),
            budget=TokenBudget(total=1500),
        )

        assert "Existing theme description" in data["existing_tests"]
        assert "Allow discount TCS" in data["related_tests"]
