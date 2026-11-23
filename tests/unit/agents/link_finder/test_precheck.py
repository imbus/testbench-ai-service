"""The precheck answers 409 with a reason before anything runs, or passes the search space."""

from types import SimpleNamespace

import pytest

from testbench_ai_service.agents.link_finder import agent as agent_module
from testbench_ai_service.agents.link_finder.agent import LinkFinder
from testbench_ai_service.agents.link_finder.model import LinkFinderArgs
from testbench_ai_service.models.agent import ElementType
from testbench_ai_service.models.language import LanguageOption
from testbench_ai_service.models.testbench import RequirementAssignment
from testbench_ai_service.utils.i18n import load_translations
from testbench_ai_service.utils.rm_service import Requirement
from tests.unit.utils.traceability.fakes import case, test_case_set

load_translations()

REQ = "473"
RM = LinkFinderArgs(rm_service_url="http://rm/", rm_username="u", rm_password="p")


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
            "linked": test_case_set("linked", "/L", links=[REQ], cases=[case("TC-L")]),
            "case": test_case_set("case", "/C", cases=[case("TC-C", links=[REQ])]),
            "y": test_case_set("y", "/Y", cases=[case("TC-Y")]),
            "x": test_case_set("x", "/X", links=["999"], cases=[case("TC-X")]),
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


async def test_the_unlinked_sets_are_the_search_space(testbench):
    result = await LinkFinder(RM).precheck(_context(), None)

    assert (result.passed, result.items) == (True, ["x", "y"])
    assert result.warnings == ["2 unlinked test case sets are searched for links to EXT-1."]


async def test_a_search_space_over_the_limit_is_refused(testbench):
    # Every searched set costs prefilter tokens; the operator caps that per run.
    args = RM.model_copy(update={"max_sets_searched": 1})

    result = await LinkFinder(args).precheck(_context(), None)

    assert result.passed is False
    assert result.warnings == [
        "2 unlinked test case sets would have to be searched for EXT-1, more than the 1 "
        "allowed (max_sets_searched)."
    ]


async def test_a_requirement_without_any_link_searches_everything(testbench):
    testbench.catalog = {"y": test_case_set("y", "/Y", cases=[case("TC-Y")])}

    result = await LinkFinder(RM).precheck(_context(), None)

    assert result.items == ["y"]


async def test_without_rm_service_the_reduced_mode_is_announced(testbench):
    result = await LinkFinder().precheck(_context(), None)

    assert result.passed is True
    assert "reduced mode" in result.warnings[0]


@pytest.mark.parametrize(
    "overrides",
    [
        {"element_type": ElementType.TESTTHEME},
        {"tov_key": None},
        {"root_key": None, "root_uid": None},
    ],
)
async def test_anything_but_a_requirement_of_a_tov_is_refused(testbench, overrides):
    result = await LinkFinder(RM).precheck(_context(**overrides), None)

    assert result.passed is False
    assert "runs on a requirement" in result.warnings[0]


async def test_an_xml_tov_is_refused(testbench):
    testbench.json_tov = False

    result = await LinkFinder(RM).precheck(_context(), None)

    assert result.passed is False
    assert "XML-based" in result.warnings[0]


async def test_a_load_failure_is_refused(testbench):
    testbench.error = RuntimeError("report job failed")

    result = await LinkFinder(RM).precheck(_context(), None)

    assert result.passed is False
    assert "could not be loaded" in result.warnings[0]


async def test_nothing_left_to_search_is_refused(testbench):
    testbench.catalog = {"linked": testbench.catalog["linked"]}

    result = await LinkFinder(RM).precheck(_context(), None)

    assert result.passed is False
    assert "already linked to requirement EXT-1" in result.warnings[0]


async def test_invalid_prompt_vars_are_refused(testbench):
    context = _context(
        prompt_config=SimpleNamespace(vars={"min_confidence_for_comment": "certain"})
    )

    result = await LinkFinder(RM).precheck(context, None)

    assert result.passed is False
    assert result.warnings[0].startswith("Invalid prompt variables:")


async def test_a_passed_precheck_keeps_the_catalog_for_the_run(testbench):
    agent = LinkFinder(RM)

    await agent.precheck(_context(), None)

    assert agent._catalog is testbench.catalog


def _unassigned(key="555"):
    return Requirement(
        key=key,
        version="2",
        title="Logout",
        description="<p>A user can log out.</p>",
        status=None,
        priority=None,
        owner=None,
        documents=[],
        external_ref="EXT-9",
    )


async def test_a_requirement_the_tov_does_not_assign_is_read_from_the_rm_service(
    testbench, monkeypatch
):
    asked = []

    async def _load(conn, rm_args, tov_key, root_key, root_uid):
        asked.append((tov_key, root_key, root_uid))
        return _unassigned()

    monkeypatch.setattr(agent_module, "load_unassigned_requirement", _load)
    agent = LinkFinder(RM)

    result = await agent.precheck(_context(root_key="555", root_uid="REQ-9"), None)

    assert asked == [("42", "555", "REQ-9")]
    assert (result.passed, result.items) == (True, ["case", "linked", "x", "y"])
    assert agent._unassigned.title == "Logout"


async def test_a_requirement_neither_tov_nor_rm_service_knows_is_refused(testbench, monkeypatch):
    async def _load(*args):
        return None

    monkeypatch.setattr(agent_module, "load_unassigned_requirement", _load)

    result = await LinkFinder(RM).precheck(_context(root_key="999"), None)

    assert result.passed is False
    assert "neither in the test object version nor in the RM service" in result.warnings[0]
