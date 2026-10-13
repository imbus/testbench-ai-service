"""The precheck answers 409 with a reason before anything runs, or passes the linked sets."""

from types import SimpleNamespace

import pytest

from testbench_ai_service.agents.coverage_checker import agent as agent_module
from testbench_ai_service.agents.coverage_checker.agent import CoverageChecker
from testbench_ai_service.agents.coverage_checker.model import CoverageCheckerArgs
from testbench_ai_service.models.agent import ElementType
from testbench_ai_service.models.language import LanguageOption
from testbench_ai_service.models.testbench import RequirementAssignment
from testbench_ai_service.utils.i18n import load_translations
from tests.unit.utils.traceability.fakes import case, test_case_set

load_translations()

REQ = "473"
RM = CoverageCheckerArgs(rm_service_url="http://rm/", rm_username="u", rm_password="p")


def _context(**overrides):
    values = {
        "project_key": "7",
        "tov_key": "42",
        "cycle_key": None,
        "root_key": REQ,
        "root_uid": None,
        "element_type": ElementType.REQUIREMENT,
        "tree_type": None,
        "user_key": "me",
        "language": LanguageOption.ENGLISH,
        "prompt_config": SimpleNamespace(vars=None),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _assignment():
    return RequirementAssignment(
        key=REQ,
        name="Login",
        id="REQ-1",
        extendedId="EXT-1",
        version="1",
        owner="o",
        status="s",
        priority="p",
        repositoryId="r",
    )


@pytest.fixture
def testbench(monkeypatch):
    state = SimpleNamespace(
        json_tov=True,
        assignments=[_assignment()],
        catalog={
            "b": test_case_set("b", "/B", links=[REQ], cases=[case("TC-B")]),
            "a": test_case_set("a", "/A", cases=[case("TC-A", links=[REQ])]),
            "x": test_case_set("x", "/X", cases=[case("TC-X")]),
        },
        error=None,
    )

    def _catalog(*args):
        if state.error:
            raise state.error
        return state.catalog

    monkeypatch.setattr(agent_module, "check_min_testbench_version", lambda *args: None)
    monkeypatch.setattr(agent_module, "is_json_based_tov", lambda *args: state.json_tov)
    monkeypatch.setattr(agent_module, "get_requirements", lambda *args: state.assignments)
    monkeypatch.setattr(agent_module, "get_test_case_set_catalog", _catalog)
    return state


async def test_the_linked_sets_pass(testbench):
    result = await CoverageChecker(RM).precheck(_context(), None)

    assert (result.passed, result.items, result.warnings) == (True, ["a", "b"], [])


async def test_without_rm_service_the_reduced_mode_is_announced(testbench):
    result = await CoverageChecker().precheck(_context(), None)

    assert result.passed is True
    assert result.warnings == [
        "No RM service is configured: the aspects are derived from the requirement title only "
        "(reduced mode)."
    ]


@pytest.mark.parametrize(
    "overrides",
    [
        {"element_type": ElementType.TESTTHEME},
        {"tov_key": None},
        {"root_key": None, "root_uid": None},
    ],
)
async def test_anything_but_a_requirement_of_a_tov_is_refused(testbench, overrides):
    result = await CoverageChecker(RM).precheck(_context(**overrides), None)

    assert result.passed is False
    assert "runs on a requirement" in result.warnings[0]


async def test_the_requirement_can_be_named_by_its_id(testbench):
    result = await CoverageChecker(RM).precheck(_context(root_key=None, root_uid="EXT-1"), None)

    assert result.passed is True


async def test_an_xml_tov_is_refused(testbench):
    testbench.json_tov = False

    result = await CoverageChecker(RM).precheck(_context(), None)

    assert result.passed is False
    assert "XML-based" in result.warnings[0]


async def test_a_load_failure_is_refused(testbench):
    testbench.error = RuntimeError("report job failed")

    result = await CoverageChecker(RM).precheck(_context(), None)

    assert result.passed is False
    assert "could not be loaded" in result.warnings[0]


async def test_an_unknown_requirement_is_refused(testbench):
    result = await CoverageChecker(RM).precheck(_context(root_key="999"), None)

    assert result.passed is False
    assert result.warnings == ["Requirement 999 was not found in the test object version."]


async def test_a_requirement_without_linked_test_cases_is_refused(testbench):
    testbench.catalog = {"e": test_case_set("e", "/E", links=[REQ])}

    result = await CoverageChecker(RM).precheck(_context(), None)

    assert result.passed is False
    assert result.warnings[0].startswith("No test case is linked to requirement EXT-1.")


async def test_invalid_prompt_vars_are_refused(testbench):
    context = _context(prompt_config=SimpleNamespace(vars={"coverage_view": "everything"}))

    result = await CoverageChecker(RM).precheck(context, None)

    assert result.passed is False
    assert result.warnings[0].startswith("Invalid prompt variables:")


async def test_a_passed_precheck_keeps_the_catalog_for_the_run(testbench):
    agent = CoverageChecker(RM)

    result = await agent.precheck(_context(), None)

    assert result.passed is True
    assert agent._catalog is testbench.catalog
