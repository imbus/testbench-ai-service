"""Tests for the test idea schema, its guardrails and how the ideas are rendered."""

import pytest

from testbench_ai_service.agents.generate_test_idears.model import (
    IdeaGroup,
    Requirement,
    TestIdea,
    TestIdeaResult,
    apply_guardrails,
)
from testbench_ai_service.agents.generate_test_idears.utils import render_test_ideas
from testbench_ai_service.models.language import LanguageOption
from testbench_ai_service.utils.i18n import load_translations


def _idea(title: str, *covered: str) -> TestIdea:
    return TestIdea(title=title, description=f"About {title}.", covered_requirements=list(covered))


def _guard(result: TestIdeaResult, **overrides) -> TestIdeaResult:
    kwargs = {
        "allowed_requirements": {"ER_1", "ER_2"},
        "existing_theme_names": set(),
        "max_ideas": None,
    }
    kwargs.update(overrides)
    return apply_guardrails(result, **kwargs)


def _shape(result: TestIdeaResult) -> list[tuple[str | None, list[str]]]:
    return [(group.theme_name, [idea.title for idea in group.ideas]) for group in result.groups]


class TestSchema:
    def test_parses_the_documented_shape(self):
        result = TestIdeaResult.model_validate_json(
            '{"groups": [{"theme_name": null, "ideas": ['
            '{"title": " A ", "description": "d", "covered_requirements": ["ER_1", " "]}]}]}'
        )

        (idea,) = result.ideas
        assert idea.title == "A"
        assert idea.covered_requirements == ["ER_1"]

    def test_a_blank_theme_name_means_directly_under_the_theme(self):
        assert IdeaGroup(theme_name="  ", ideas=[]).theme_name is None

    def test_an_empty_idea_list_is_valid(self):
        assert TestIdeaResult.model_validate_json('{"groups": []}').ideas == []


class TestGuardrails:
    def test_dissolves_a_group_with_fewer_than_two_ideas(self):
        result = TestIdeaResult(
            groups=[
                IdeaGroup(theme_name="Lonely", ideas=[_idea("A")]),
                IdeaGroup(theme_name="Pair", ideas=[_idea("B"), _idea("C")]),
            ]
        )

        assert _shape(_guard(result)) == [("Pair", ["B", "C"]), (None, ["A"])]

    def test_merges_groups_of_the_same_name(self):
        result = TestIdeaResult(
            groups=[
                IdeaGroup(theme_name="Limits", ideas=[_idea("A")]),
                IdeaGroup(theme_name="limits ", ideas=[_idea("B")]),
            ]
        )

        assert _shape(_guard(result)) == [("Limits", ["A", "B"])]

    def test_puts_all_ungrouped_ideas_into_one_group_last(self):
        result = TestIdeaResult(
            groups=[
                IdeaGroup(ideas=[_idea("A")]),
                IdeaGroup(theme_name="Pair", ideas=[_idea("B"), _idea("C")]),
                IdeaGroup(ideas=[_idea("D")]),
            ]
        )

        assert _shape(_guard(result)) == [("Pair", ["B", "C"]), (None, ["A", "D"])]

    def test_renames_a_group_colliding_with_an_existing_theme(self):
        result = TestIdeaResult(
            groups=[IdeaGroup(theme_name="Rebates", ideas=[_idea("A"), _idea("B")])]
        )

        guarded = _guard(result, existing_theme_names={"rebates", "Rebates (2)"})

        assert _shape(guarded) == [("Rebates (3)", ["A", "B"])]

    def test_keeps_only_the_themes_own_requirements(self):
        result = TestIdeaResult(groups=[IdeaGroup(ideas=[_idea("A", "ER_1", "CTX_9", "ER_1")])])

        (idea,) = _guard(result).ideas
        assert idea.covered_requirements == ["ER_1"]

    def test_removes_duplicate_titles(self):
        result = TestIdeaResult(
            groups=[
                IdeaGroup(theme_name="Pair", ideas=[_idea("A"), _idea("B")]),
                IdeaGroup(ideas=[_idea(" a "), _idea("C")]),
            ]
        )

        assert _shape(_guard(result)) == [("Pair", ["A", "B"]), (None, ["C"])]

    def test_drops_ideas_without_a_title(self):
        result = TestIdeaResult(groups=[IdeaGroup(ideas=[_idea(" "), _idea("A")])])

        assert _shape(_guard(result)) == [(None, ["A"])]

    def test_caps_the_total_and_dissolves_groups_the_cap_leaves_too_small(self):
        result = TestIdeaResult(
            groups=[
                IdeaGroup(theme_name="First", ideas=[_idea("A"), _idea("B")]),
                IdeaGroup(theme_name="Second", ideas=[_idea("C"), _idea("D")]),
            ]
        )

        assert _shape(_guard(result, max_ideas=3)) == [("First", ["A", "B"]), (None, ["C"])]

    def test_an_empty_result_stays_empty(self):
        assert _guard(TestIdeaResult(groups=[])).groups == []

    def test_leaves_the_input_unchanged(self):
        result = TestIdeaResult(groups=[IdeaGroup(ideas=[_idea("A", "CTX_9")])])

        _guard(result)

        assert result.ideas[0].covered_requirements == ["CTX_9"]


def _requirement(external_ref: str, title: str) -> Requirement:
    return Requirement(
        key="1",
        version="1",
        title=title,
        description=None,
        status=None,
        priority=None,
        owner=None,
        documents=[],
        external_ref=external_ref,
    )


class TestRenderTestIdeas:
    @pytest.fixture(autouse=True)
    def setup(self):
        load_translations()

    def test_renders_subthemes_then_ideas_directly_under_the_theme(self):
        result = TestIdeaResult(
            groups=[
                IdeaGroup(theme_name="Limits", ideas=[_idea("A", "ER_1"), _idea("B")]),
                IdeaGroup(ideas=[_idea("C", "ER_1", "ER_2")]),
            ]
        )

        text = render_test_ideas(
            result,
            [_requirement("ER_1", "Discount"), _requirement("ER_2", "Rebate")],
            LanguageOption.ENGLISH,
        )

        assert text == (
            "Test ideas for:\n"
            "ER_1: Discount\n"
            "ER_2: Rebate\n"
            "\n"
            "1 Test theme: Limits\n"
            "\n"
            "   1.1 Test case: A\n"
            "      About A.\n"
            "      Covers: ER_1\n"
            "\n"
            "   1.2 Test case: B\n"
            "      About B.\n"
            "\n"
            "2 Test case: C\n"
            "   About C.\n"
            "   Covers: ER_1, ER_2"
        )

    def test_uses_the_language_of_the_run(self):
        result = TestIdeaResult(groups=[IdeaGroup(ideas=[_idea("A")])])

        text = render_test_ideas(result, [_requirement("ER_1", "Rabatt")], LanguageOption.GERMAN)

        assert text.startswith("Testideen zu:\nER_1: Rabatt\n\n1 Testfall: A")

    def test_renders_a_notice_for_an_empty_result(self):
        text = render_test_ideas(
            TestIdeaResult(groups=[]), [_requirement("ER_1", "Discount")], LanguageOption.ENGLISH
        )

        assert text == "Test ideas for:\nER_1: Discount\n\nNo new test ideas were generated."
