"""The coverage check end to end, with the model and TestBench replaced."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from testbench_ai_service.agents.coverage_checker import agent as agent_module
from testbench_ai_service.agents.coverage_checker.agent import CoverageChecker
from testbench_ai_service.agents.coverage_checker.model import (
    CoverageCheckerArgs,
    CoverageResult,
    GapExplanation,
    GapList,
    SuggestedTest,
)
from testbench_ai_service.jobs.handle import JobHandle, job_scope
from testbench_ai_service.jobs.store import JobStore
from testbench_ai_service.models.language import LanguageOption
from testbench_ai_service.utils.i18n import get_translation, load_translations
from testbench_ai_service.utils.rm_service import Requirement
from testbench_ai_service.utils.structured_output import StructuredOutputError
from testbench_ai_service.utils.traceability.models import (
    Aspect,
    AspectEvidence,
    AspectList,
    LinkedSet,
    RequirementContext,
    SetInterpretation,
    TestCase,
)
from testbench_ai_service.utils.traceability.review_writer import WriteOutcome

load_translations()

DESCRIPTION = "<p>A user can log in. After 3 failed attempts the account is locked.</p>"


def _context(prompt_vars=None):
    return SimpleNamespace(
        project_key="7",
        tov_key="42",
        root_key="473",
        root_uid=None,
        user_key="me",
        language=LanguageOption.ENGLISH,
        llm_config=SimpleNamespace(model="m", model_extra={}),
        prompt_config=SimpleNamespace(
            file="coverage_checker/prompt.yaml", variant=None, vars=prompt_vars
        ),
    )


def _set(key, cases=("TC-1",), status="Released"):
    return LinkedSet(
        key=key,
        spec_key=f"spec-{key}",
        unique_id=f"U-{key}",
        title=f"Set {key}",
        path=f"/Auth/{key}",
        description="",
        spec_status=status,
        linked_as_whole=True,
        test_cases=[TestCase(key=f"{c}-{key}", parameters={}, calls=[]) for c in cases],
    )


def _loaded(*linked_sets, description=DESCRIPTION):
    requirement = Requirement(
        key="473",
        version="1",
        title="Login",
        description=description,
        status=None,
        priority=None,
        owner=None,
        documents=[],
        external_ref="REQ-42",
    )
    return RequirementContext(
        requirement=requirement, linked_sets=list(linked_sets), reduced_mode=description is None
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


def _evidence(key, aspect_id="A1", strength="full"):
    return SetInterpretation(
        evidence=[
            AspectEvidence(aspect_id=aspect_id, test_case_key=key, strength=strength, evidence="e")
        ]
    )


@pytest.fixture
def world(monkeypatch):
    """Replaces TestBench and the model; tests fill in what each step answers."""
    state = SimpleNamespace(
        loaded=_loaded(_set("s1"), _set("s2"), _set("s3", cases=())),
        interpretations={"s1": _evidence("TC-1-s1"), "s2": SetInterpretation(evidence=[])},
        aspects=ASPECTS,
        gaps=GapList(
            gaps=[
                GapExplanation(
                    aspect_id="A2",
                    gap_reason="No test fails three times.",
                    suggested_test=SuggestedTest(title="Lock after third failure", description="d"),
                )
            ]
        ),
        steps=[],
        writes={},
        locked=set(),
    )

    async def _load(*args, **kwargs):
        state.load_kwargs = kwargs
        return state.loaded

    async def _ai(self, llm_client, llm_config, prompt_config, schema, agent_data=None, step=None):
        state.steps.append(step)
        if step == "aspects":
            answer = state.aspects
        elif step == "interpretation":
            set_title = agent_data["test_case_set"].split(" (")[0]
            answer = state.interpretations[set_title.removeprefix("Set ")]
        else:
            answer = state.gaps
        if isinstance(answer, Exception):
            raise answer
        return answer

    async def _write(conn, project_key, tov_key, user_key, linked_set, pattern, block):
        if linked_set.key in state.locked:
            return WriteOutcome.LOCKED
        state.writes[linked_set.key] = block
        return WriteOutcome.WRITTEN

    monkeypatch.setattr(agent_module, "load_requirement_context", _load)
    monkeypatch.setattr(agent_module, "write_review_block", _write)
    monkeypatch.setattr(CoverageChecker, "get_structured_ai_response", _ai)
    return state


async def _check(prompt_vars=None, args=None):
    return await CoverageChecker(args or CoverageCheckerArgs()).check_coverage(
        _context(prompt_vars), None, None, ["s1", "s2", "s3"]
    )


async def test_the_matrix_is_built_explained_and_written_to_every_set(world):
    result = await _check()

    assert result.summary() == "2 aspects: 1 covered, 0 weak, 1 missing"
    assert [(c.aspect.id, c.status) for c in result.aspects] == [
        ("A1", "covered"),
        ("A2", "missing"),
    ]
    assert result.aspects[1].suggested_test.title == "Lock after third failure"
    assert [(s.set_key, s.reason) for s in result.sets_without_evidence] == [
        ("s2", "no_matching_aspect"),
        ("s3", "no_test_cases"),
    ]
    assert world.steps.count("interpretation") == 2  # s3 has no test cases to read
    assert set(world.writes) == {"s1", "s2", "s3"}
    assert "Proves for REQ-42: A1 (full)." in world.writes["s1"]
    assert "tests none of its aspects" in world.writes["s2"]
    assert (result.incomplete, result.reduced_mode, result.skipped_comments) == (False, False, [])


async def test_full_coverage_asks_no_gaps(world):
    world.interpretations["s2"] = _evidence("TC-1-s2", aspect_id="A2")

    result = await _check()

    assert "gaps" not in world.steps
    assert {c.status for c in result.aspects} == {"covered"}


async def test_a_set_that_cannot_be_interpreted_leaves_the_others_intact(world):
    world.interpretations["s2"] = StructuredOutputError("bad", raw_response="?")

    result = await _check()

    assert result.incomplete is True
    assert ("s2", "interpretation_failed") in [
        (s.set_key, s.reason) for s in result.sets_without_evidence
    ]
    assert set(world.writes) == {"s1", "s2", "s3"}


async def test_a_failed_gap_step_still_writes_the_matrix(world):
    world.gaps = StructuredOutputError("bad", raw_response="?")

    result = await _check()

    assert result.aspects[1].gap_reason is None
    assert set(world.writes) == {"s1", "s2", "s3"}


async def test_a_failed_aspect_step_writes_nothing(world):
    world.aspects = AspectList(
        aspects=[Aspect(id="x", statement="Invented", kind="negative", source_quote="not in text")]
    )

    assert await _check() is None
    assert world.writes == {}
    assert "interpretation" not in world.steps


async def test_writing_can_be_switched_off_per_run(world):
    result = await _check({"write_review_comments": "false"})

    assert result is not None
    assert world.writes == {}


async def test_a_locked_set_is_reported_as_skipped(world):
    world.locked = {"s2"}

    result = await _check()

    assert result.skipped_comments == ["s2"]


async def test_the_work_view_counts_unreleased_sets(world):
    world.loaded = _loaded(_set("s1", status="InProgress"), _set("s2"), _set("s3", cases=()))

    release = await _check()
    work = await _check({"coverage_view": "work"})

    assert (release.aspects[0].status, release.aspects[0].weak_reason) == (
        "weak",
        "set_not_released",
    )
    assert work.aspects[0].status == "covered"


async def test_run_logs_the_report(world, monkeypatch):
    logger = MagicMock()
    monkeypatch.setattr(agent_module, "logger", logger)

    await CoverageChecker().run(_context(), None, None, ["s1", "s2", "s3"])

    message = logger.info.call_args.args[0] % logger.info.call_args.args[1:]
    assert "Coverage of REQ-42: 2 aspects: 1 covered, 0 weak, 1 missing" in message
    assert '"requirement_key": "REQ-42"' in message


async def test_no_loadable_sets_stops_before_any_model_call(world):
    world.loaded = _loaded()

    assert await _check() is None
    assert world.steps == []
    assert world.writes == {}


async def test_a_failing_block_rendering_only_fails_that_set(world, monkeypatch):
    original = agent_module.render_set_block

    def _render(result, set_key, *args):
        if set_key == "s2":
            raise RuntimeError("boom")
        return original(result, set_key, *args)

    monkeypatch.setattr(agent_module, "render_set_block", _render)

    result = await _check()

    assert set(world.writes) == {"s1", "s3"}
    assert result.skipped_comments == ["s2"]


async def test_run_reuses_the_catalog_the_precheck_loaded(world):
    agent = CoverageChecker()
    agent._catalog = {"cat": "alog"}

    await agent.check_coverage(_context(), None, None, ["s1"])

    assert world.load_kwargs["catalog"] == {"cat": "alog"}


async def test_run_without_precheck_loads_the_catalog_itself(world):
    await CoverageChecker().check_coverage(_context(), None, None, ["s1"])

    assert world.load_kwargs["catalog"] is None


class TestJobReporting:
    @pytest.fixture
    def job(self, tmp_path):
        store = JobStore(tmp_path / "usage.sqlite")
        store.create(
            "j1",
            agent_key="coverage_checker",
            user_key="me",
            project_key="7",
            project_name="P",
            root_key="473",
            item_ids=["s1", "s2", "s3"],
            warnings=[],
        )
        return SimpleNamespace(store=store, handle=JobHandle("j1", store))

    @staticmethod
    def _text(key, **values):
        return get_translation(f"coverage_checker.job.{key}", LanguageOption.ENGLISH, **values)

    async def _run(self, job, item_ids=("s1", "s2", "s3")):
        with job_scope(job.handle):
            await CoverageChecker().run(_context(), None, None, list(item_ids))
        return job.store.get("j1", "me")

    async def test_successful_check_stores_full_result_as_report(self, world, job):
        detail = await self._run(job)

        assert detail.report_type == "coverage_checker"
        assert CoverageResult.model_validate(detail.report).requirement_key == "REQ-42"
        assert job.handle.failed is False

    async def test_progress_counts_interpreted_sets(self, world, job):
        world.loaded = _loaded(_set("s1"), _set("s2"))

        detail = await self._run(job, ["s1", "s2"])

        assert (detail.progress.done, detail.progress.total) == (2, 2)
        assert detail.progress.text == self._text("progress.gaps")

    async def test_sets_progress_text_is_reported_while_interpreting(self, world, job, monkeypatch):
        seen = []
        original = job.handle.progress

        async def _spy(done, total, text=None):
            seen.append((done, total, text))
            await original(done, total, text)

        monkeypatch.setattr(job.handle, "progress", _spy)

        await self._run(job)

        assert seen[0] == (0, 3, self._text("progress.aspects"))
        assert (2, 3, self._text("progress.sets")) in seen
        assert seen[-1] == (3, 3, self._text("progress.gaps"))

    @pytest.mark.parametrize(
        ("case", "key", "requirement"),
        [
            ("no_items", "nothing_to_check", None),
            ("load_raises", "load_failed", "473"),
            ("no_sets", "no_sets_loaded", "REQ-42"),
            ("decompose_raises", "decompose_failed", "REQ-42"),
        ],
    )
    async def test_early_stop_fails_job_with_reason(
        self, case, key, requirement, world, job, monkeypatch
    ):
        item_ids = ["s1", "s2", "s3"]
        if case == "no_items":
            item_ids = []
        elif case == "load_raises":

            async def _boom(*args, **kwargs):
                raise RuntimeError("down")

            monkeypatch.setattr(agent_module, "load_requirement_context", _boom)
        elif case == "no_sets":
            world.loaded = _loaded()
        else:
            world.aspects = StructuredOutputError("bad", raw_response="?")

        detail = await self._run(job, item_ids)

        values = {"requirement": requirement} if requirement else {}
        assert detail.error == self._text(key, **values)
        assert detail.status == "failed"
        assert detail.report is None
        assert job.handle.failed is True

    async def test_incomplete_result_is_still_a_report_not_a_failure(self, world, job):
        world.interpretations["s2"] = StructuredOutputError("bad", raw_response="?")

        detail = await self._run(job)

        assert detail.report["incomplete"] is True
        assert job.handle.failed is False

    async def test_without_job_scope_run_is_unchanged(self, world):
        await CoverageChecker().run(_context(), None, None, ["s1", "s2", "s3"])
