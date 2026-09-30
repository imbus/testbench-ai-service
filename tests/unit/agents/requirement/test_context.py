"""Tests for rendering the context sent to the model."""

from testbench_ai_service.agents.generate_test_idears.context import (
    assemble_context,
    html_text,
    render_existing_tests,
    render_requirement,
    strip_generated_ideas,
)
from testbench_ai_service.agents.generate_test_idears.model import (
    ExistingTestCaseSet,
    Requirement,
    Theme,
    ThemeContext,
)

#: A theme description as TestBench stores it after an earlier run: text written
#: by a user, then the ideas block ``template.jinja`` rendered.
DESCRIPTION_WITH_IDEAS = """<html><body>
    <p>Written by a tester.</p><br /><br />
    <b>AI Test Ideas - 2026-09-28 12:27:27</b><br />
    <div style="white-space: pre-wrap;">1 Test case: Discount of 0%<br />   Details</div>
    <div style="padding-top: 5px;">
      <div style="border-top: 1px solid black; width: 218px; font-size: 10px;">
        AI-generated responses may be inaccurate.
      </div>
    </div>
  </body></html>"""


def _requirement(external_ref: str = "ER_1", **overrides) -> Requirement:
    fields = {
        "key": "473",
        "version": "1",
        "title": "Automatic discount",
        "description": None,
        "status": "open",
        "priority": "high",
        "owner": "someone",
        "documents": [],
        "external_ref": external_ref,
    }
    return Requirement(**(fields | overrides))


def _test_case_set(
    path: str, requirement_keys: list[str], description: str = ""
) -> ExistingTestCaseSet:
    return ExistingTestCaseSet(
        key=path,
        title=path.rsplit("/", 1)[-1],
        path=path,
        description_short=description,
        requirement_keys=requirement_keys,
    )


class TestRenderRequirement:
    def test_renders_identifier_title_and_attributes(self):
        assert render_requirement(_requirement()) == (
            "- ER_1: Automatic discount\n"
            "  version: 1 | status: open | priority: high | owner: someone"
        )

    def test_omits_empty_attributes(self):
        rendered = render_requirement(_requirement(owner=None, priority=None))

        assert rendered.splitlines()[1] == "  version: 1 | status: open"

    def test_falls_back_to_the_key_without_an_external_ref(self):
        rendered = render_requirement(_requirement(external_ref=None))

        assert rendered.splitlines()[0] == "- 473: Automatic discount"

    def test_renders_description_indented_below_attributes(self):
        requirement = _requirement(description="Orders above 100 EUR\nget 5 % off.")

        assert render_requirement(requirement).splitlines()[2:] == [
            "  description:",
            "    Orders above 100 EUR",
            "    get 5 % off.",
        ]

    def test_omits_description_without_visible_text(self):
        requirement = _requirement(description="<p> </p>")

        assert len(render_requirement(requirement).splitlines()) == 2

    def test_leaves_out_an_html_header_of_the_description(self):
        requirement = _requirement(
            description="<header>\n<h1>Spec v2</h1>\n</header>\n<p>Orders get 5 % off.</p>"
        )

        assert render_requirement(requirement).splitlines()[2:] == [
            "  description:",
            "    <p>Orders get 5 % off.</p>",
        ]

    def test_omits_a_description_that_is_only_a_header(self):
        requirement = _requirement(description="<header><h1>Spec v2</h1></header>")

        assert len(render_requirement(requirement).splitlines()) == 2

    def test_lists_the_test_case_sets_covering_it(self):
        rendered = render_requirement(_requirement(), ["A/TCS 1", "TCS 2"])

        assert rendered.splitlines()[-1] == "  existing test case sets: A/TCS 1, TCS 2"

    def test_says_none_when_nothing_covers_it(self):
        rendered = render_requirement(_requirement(), [])

        assert rendered.splitlines()[-1] == "  existing test case sets: none"


class TestHtmlText:
    def test_collapses_the_visible_text(self):
        assert html_text("<html><body><p>Orders</p>\n  <p>get 5 % off.</p></body></html>") == (
            "Orders get 5 % off."
        )

    def test_leaves_out_every_header(self):
        html = (
            '<html><body><HEADER class="top">Logo</HEADER>'
            "<p>Orders get 5 % off.</p><header>Nav</header></body></html>"
        )

        assert html_text(html) == "Orders get 5 % off."


class TestStripGeneratedIdeas:
    def test_removes_an_earlier_ideas_block_and_keeps_the_rest(self):
        stripped = strip_generated_ideas(DESCRIPTION_WITH_IDEAS)

        assert "Written by a tester." in stripped
        assert "Test Ideas" not in stripped
        assert "Discount of 0%" not in stripped
        assert "inaccurate" not in stripped

    def test_leaves_a_description_without_ideas_alone(self):
        html = "<html><body><b>Scope</b><br/>Discounts only</body></html>"

        assert strip_generated_ideas(html) == html


class TestRenderExistingTests:
    def test_renders_the_theme_and_what_is_below_it(self):
        theme_context = ThemeContext(
            theme=Theme(
                key="1",
                title="discount",
                description="<html><body>Old</body></html>",
                review_comment="<html><body>Cover the edge cases</body></html>",
                path=["plattform tests", "discount"],
                priority="High",
                tags=["smoke"],
                udfs={"Component": "Pricing"},
            ),
            existing_subthemes=["Sub"],
            existing_test_case_sets=[
                _test_case_set("Sub/TCS 1", [], "Checks the rebate"),
                _test_case_set("TCS 2", []),
            ],
        )

        assert render_existing_tests(theme_context) == (
            "Test theme: discount\n"
            "Path: plattform tests / discount\n"
            "Priority: High\n"
            "Tags: smoke\n"
            "Component: Pricing\n"
            "Current description: Old\n"
            "Review comment: Cover the edge cases\n"
            "Test themes already below this theme:\n"
            "- Sub\n"
            "Test case sets already below this theme:\n"
            "- Sub/TCS 1: Checks the rebate\n"
            "- TCS 2"
        )

    def test_leaves_out_what_is_empty(self):
        theme_context = ThemeContext(
            theme=Theme(key="1", title="Discounts", description="<html><body> </body></html>")
        )

        assert render_existing_tests(theme_context) == "Test theme: Discounts"

    def test_leaves_out_ideas_written_by_an_earlier_run(self):
        theme_context = ThemeContext(
            theme=Theme(key="1", title="Discounts", description=DESCRIPTION_WITH_IDEAS)
        )

        assert render_existing_tests(theme_context).splitlines()[1] == (
            "Current description: Written by a tester."
        )


def test_coverage_maps_every_requirement_to_the_sets_linked_to_it():
    theme_context = ThemeContext(
        theme=Theme(key="1", title="Discounts"),
        requirements=[_requirement("ER_1", key="1"), _requirement("ER_2", key="2")],
        existing_test_case_sets=[
            _test_case_set("TCS 1", ["1", "99"]),
            _test_case_set("TCS 2", ["1"]),
        ],
    )

    assert theme_context.coverage() == {"1": ["TCS 1", "TCS 2"], "2": []}


def test_assemble_context_renders_one_entry_per_requirement_in_order():
    agent_data = assemble_context(
        ThemeContext(
            theme=Theme(key="1", title="Discounts"),
            requirements=[_requirement("ER_1", key="1"), _requirement("ER_2", key="2")],
            existing_test_case_sets=[_test_case_set("TCS 1", ["2"])],
        )
    )

    assert [entry.splitlines()[0] for entry in agent_data["requirements"]] == [
        "- ER_1: Automatic discount",
        "- ER_2: Automatic discount",
    ]
    assert agent_data["requirements"][1].splitlines()[-1] == "  existing test case sets: TCS 1"
    assert agent_data["existing_tests"] == (
        "Test theme: Discounts\nTest case sets already below this theme:\n- TCS 1"
    )
