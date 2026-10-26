"""The link search end to end, with the model and TestBench replaced."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from testbench_ai_service.agents.link_finder import agent as agent_module
from testbench_ai_service.agents.link_finder.agent import LinkFinder
from testbench_ai_service.agents.link_finder.model import (
    LinkFinderArgs,
    PrefilterAnswer,
    PrefilterHit,
)
from testbench_ai_service.models.language import LanguageOption
from testbench_ai_service.models.testbench import RequirementAssignment
from testbench_ai_service.utils.i18n import load_translations
from testbench_ai_service.utils.rm_service import Requirement
from testbench_ai_service.utils.structured_output import StructuredOutputError
from testbench_ai_service.utils.traceability.context import RequirementNotFoundError
from testbench_ai_service.utils.traceability.models import (
    Aspect,
    AspectEvidence,
    AspectList,
    SetInterpretation,
)
from testbench_ai_service.utils.traceability.review_writer import WriteOutcome, render_block
from tests.unit.utils.traceability.fakes import case, test_case_set

load_translations()

REQ = "473"
DESCRIPTION = "<p>A user can log in. After 3 failed attempts the account is locked.</p>"


def _context(prompt_vars=None):
    return SimpleNamespace(
        project_key="7",
        tov_key="42",
        root_key=REQ,
        root_uid=None,
        user_key="me",
        language=LanguageOption.ENGLISH,
        llm_config=SimpleNamespace(model="m", model_extra={}),
        prompt_config=SimpleNamespace(
            file="link_finder/prompt.yaml", variant=None, vars=prompt_vars
        ),
    )


def _requirement(description=DESCRIPTION):
    return Requirement(
        key=REQ,
        version="1",
        title="Login",
        description=description,
        status=None,
        priority=None,
        owner=None,
        documents=[],
        external_ref="REQ-42",
    )


def _assignment(key, extended):
    return RequirementAssignment(
        key=key,
        name="n",
        id="i",
        extendedId=extended,
        version="1",
        owner="o",
        status="s",
        priority="p",
        repositoryId="r",
    )


ASPECTS = AspectList(
    aspects=[
        Aspect(
            id="x", statement="Login succeeds", kind="happy_path", source_quote="a user can log in"
        ),
        Aspect(
            id="y",
            statement="Lock after 3 failures",
            kind="boundary",
            source_quote="after 3 failed attempts",
        ),
    ]
)


def _evidence(*items):
    return SetInterpretation(
        evidence=[
            AspectEvidence(aspect_id=aspect, test_case_key=key, strength=strength, evidence="e")
            for aspect, key, strength in items
        ]
    )


def _catalog():
    return {
        "lock": test_case_set("lock", "/Auth/Lock", links=["900"], cases=[case("TC-lock")]),
        "login": test_case_set("login", "/Auth/Login", cases=[case("TC-login")]),
        "touch": test_case_set("touch", "/Auth/Touch", cases=[case("TC-touch")]),
        "empty": test_case_set("empty", "/Auth/Empty"),
        "report": test_case_set("report", "/Reporting", cases=[case("TC-report")]),
    }


@pytest.fixture
def world(monkeypatch):
    """Replaces TestBench and the model; tests fill in what each step answers."""
    state = SimpleNamespace(
        requirement=_requirement(),
        assignments=[_assignment(REQ, "REQ-42"), _assignment("900", "REQ-7")],
        catalog=_catalog(),
        aspects=ASPECTS,
        hits=[
            PrefilterHit(set_key=key, relevance="medium", reason="r")
            for key in ("lock", "login", "touch", "empty")
        ],
        interpretations={
            "lock": _evidence(("A1", "TC-lock", "full"), ("A2", "TC-lock", "full")),
            "login": _evidence(("A1", "TC-login", "full")),
            "touch": _evidence(("A2", "TC-touch", "partial")),
        },
        steps=[],
        writes={},
        removed=[],
        locked=set(),
    )

    async def _load(*args):
        return state.requirement, state.assignments

    async def _ai(self, llm_client, llm_config, prompt_config, schema, agent_data=None, step=None):
        state.steps.append(step)
        if step == "aspects":
            answer = state.aspects
        elif step == "prefilter":
            answer = (
                state.hits
                if isinstance(state.hits, Exception)
                else PrefilterAnswer(hits=state.hits)
            )
        else:
            set_key = agent_data["test_case_set"].split(" (")[0].removeprefix("Set ")
            answer = state.interpretations[set_key]
        if isinstance(answer, Exception):
            raise answer
        return answer

    async def _write(conn, project_key, tov_key, user_key, detail, pattern, block):
        if detail.key in state.locked:
            return WriteOutcome.LOCKED
        state.writes[detail.key] = block
        return WriteOutcome.WRITTEN

    async def _remove(conn, project_key, tov_key, user_key, detail, pattern):
        state.removed.append(detail.key)
        return WriteOutcome.WRITTEN

    monkeypatch.setattr(agent_module, "load_requirement", _load)
    monkeypatch.setattr(agent_module, "write_review_block", _write)
    monkeypatch.setattr(agent_module, "remove_review_block", _remove)
    monkeypatch.setattr(LinkFinder, "get_structured_ai_response", _ai)
    return state


ITEMS = ["empty", "lock", "login", "touch", "report"]


async def _find(world, prompt_vars=None, args=None, items=ITEMS):
    agent = LinkFinder(args or LinkFinderArgs())
    agent._catalog = world.catalog
    return await agent.find_links(_context(prompt_vars), None, None, items)


async def test_candidates_are_ranked_and_every_one_commented(world):
    result = await _find(world)

    assert [(c.set_key, c.confidence) for c in result.candidates] == [
        ("lock", "high"),
        ("login", "high"),
        ("touch", "low"),
    ]
    assert result.candidates[0].already_linked_to == ["REQ-7"]
    assert result.candidates[0].covered_aspect_ids == ["A1", "A2"]
    assert result.empty_sets == ["empty"]
    assert (result.sets_screened, result.sets_detailed) == (5, 4)
    assert set(world.writes) == {"lock", "login", "touch"}  # low ones too
    assert "Already linked to REQ-7" in world.writes["lock"]
    assert world.steps.count("interpretation") == 3  # the empty set is not read
    assert (result.incomplete, result.reduced_mode, result.skipped_comments) == (False, False, [])


async def test_the_comment_threshold_can_be_raised_per_run(world):
    await _find(world, {"min_confidence_for_comment": "medium"})

    assert set(world.writes) == {"lock", "login"}  # low stays in the log


async def test_writing_can_be_switched_off_per_run(world):
    result = await _find(world, {"write_review_comments": "false"})

    assert result.candidates
    assert (world.writes, world.removed) == ({}, [])


async def test_no_prefilter_hit_is_a_valid_result(world):
    world.hits = []

    result = await _find(world)

    assert (result.candidates, result.sets_detailed) == ([], 0)
    assert "interpretation" not in world.steps


async def test_a_failing_candidate_leaves_the_others_intact(world):
    world.interpretations["login"] = StructuredOutputError("bad", raw_response="?")

    result = await _find(world)

    assert result.failed_sets == ["login"]
    assert result.incomplete is True
    assert [c.set_key for c in result.candidates] == ["lock", "touch"]


async def test_a_failed_prefilter_still_returns_an_incomplete_result(world):
    world.hits = StructuredOutputError("bad", raw_response="?")

    result = await _find(world)

    assert (result.candidates, result.incomplete) == ([], True)


async def test_a_failed_aspect_step_writes_nothing(world):
    world.aspects = AspectList(
        aspects=[Aspect(id="x", statement="Invented", kind="negative", source_quote="not in text")]
    )

    assert await _find(world) is None
    assert "prefilter" not in world.steps
    assert world.writes == {}


async def test_reduced_mode_lowers_every_confidence(world):
    world.requirement = _requirement(description=None)
    world.aspects = AspectList(
        aspects=[Aspect(id="x", statement="Login", kind="happy_path", source_quote="Login")]
    )
    world.interpretations = {
        "lock": _evidence(("A1", "TC-lock", "full")),
        "login": _evidence(("A1", "TC-login", "partial")),
        "touch": _evidence(),
    }

    result = await _find(world)

    assert result.reduced_mode is True
    assert [(c.set_key, c.confidence) for c in result.candidates] == [("lock", "medium")]
    assert "title only" in world.writes["lock"]


async def test_a_locked_candidate_is_reported_as_skipped(world):
    world.locked = {"login"}

    result = await _find(world)

    assert result.skipped_comments == ["login"]


async def test_outdated_blocks_of_this_requirement_are_removed(world):
    old = render_block("AI Link Candidate", "REQ-42", "old", "d", "t0")
    world.catalog["report"].details.spec.reviewComment = old  # no longer a candidate
    world.catalog["lock"].details.spec.reviewComment = old  # candidate again: rewritten
    world.catalog["linked"] = test_case_set(
        "linked", "/Linked", links=[REQ], review_comment=f"<p>note</p><br/>{old}"
    )
    world.catalog["other"] = test_case_set(
        "other", "/Other", review_comment=render_block("AI Link Candidate", "REQ-43", "o", "d", "t")
    )

    await _find(world)

    assert sorted(world.removed) == ["linked", "report"]
    assert "lock" in world.writes


async def test_a_set_the_prefilter_could_not_screen_keeps_its_block(world):
    # Its hint from an earlier run is not outdated: this run never looked at the set.
    world.catalog["report"].details.spec.reviewComment = render_block(
        "AI Link Candidate", "REQ-42", "old", "d", "t0"
    )
    world.hits = StructuredOutputError("bad", raw_response="?")

    await _find(world)

    assert world.removed == []


async def test_a_candidate_whose_interpretation_failed_keeps_its_block(world):
    world.catalog["login"].details.spec.reviewComment = render_block(
        "AI Link Candidate", "REQ-42", "old", "d", "t0"
    )
    world.interpretations["login"] = RuntimeError("model down")

    await _find(world)

    assert "login" not in world.removed


async def test_run_logs_the_report(world, monkeypatch):
    logger = MagicMock()
    monkeypatch.setattr(agent_module, "logger", logger)
    agent = LinkFinder()
    agent._catalog = world.catalog

    await agent.run(_context(), None, None, ITEMS)

    message = logger.info.call_args.args[0] % logger.info.call_args.args[1:]
    assert "Link candidates for REQ-42: 3 candidates (2 high, 0 medium, 1 low)" in message
    assert "Candidates already linked to other requirements" in message
    assert '"requirement_key": "REQ-42"' in message


async def test_no_loadable_sets_stops_before_any_model_call(world):
    assert await _find(world, items=["gone"]) is None
    assert world.steps == []


async def test_run_without_precheck_loads_the_catalog_itself(world, monkeypatch):
    monkeypatch.setattr(agent_module, "get_test_case_set_catalog", lambda *args: world.catalog)

    result = await LinkFinder().find_links(_context(), None, None, ITEMS)

    assert len(result.candidates) == 3


async def test_a_requirement_the_tov_does_not_assign_comes_from_the_precheck(world, monkeypatch):
    async def _not_in_tov(*args):
        raise RequirementNotFoundError("not in TOV")

    monkeypatch.setattr(agent_module, "load_requirement", _not_in_tov)
    monkeypatch.setattr(agent_module, "get_requirements", lambda *args: world.assignments)
    agent = LinkFinder(LinkFinderArgs())
    agent._catalog = world.catalog
    agent._unassigned = _requirement()

    result = await agent.find_links(_context(), None, None, ITEMS)

    assert result.requirement_key == "REQ-42"
    assert [c.set_key for c in result.candidates] == ["lock", "login", "touch"]


async def test_a_requirement_nobody_knows_stops_the_run(world, monkeypatch):
    async def _not_in_tov(*args):
        raise RequirementNotFoundError("not in TOV")

    async def _not_in_rm(*args):
        return None

    monkeypatch.setattr(agent_module, "load_requirement", _not_in_tov)
    monkeypatch.setattr(agent_module, "load_unassigned_requirement", _not_in_rm)

    assert await _find(world) is None
    assert world.steps == []
