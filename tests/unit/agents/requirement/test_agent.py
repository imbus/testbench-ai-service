"""Tests for the requirement agent's orchestration and write-back sequence."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from testbench_ai_service.agents.requirement import agent as agent_module
from testbench_ai_service.agents.requirement.agent import RequirementAgent
from testbench_ai_service.models.language import LanguageOption
from testbench_ai_service.models.testbench import RequirementAssignment, TestThemeNode


def _context(user_key: str = "u1") -> SimpleNamespace:
    return SimpleNamespace(
        user_key=user_key,
        project_name="VSR-Dreamcar",
        project_key="10004",
        tov_key="42",
        cycle_key=None,
        root_uid="TT-1",
        filtering=None,
        language=LanguageOption.ENGLISH,
        llm_config=SimpleNamespace(model="gpt-4.1-mini", model_extra={}),
        prompt_config=SimpleNamespace(file="requirement/prompt.yaml", variant="Default"),
        templates_dir=Path("templates"),
    )


def _theme_node(locker_key: str | None = None) -> MagicMock:
    theme = MagicMock(spec=TestThemeNode)
    theme.base = SimpleNamespace(name="Discounts", key="k-s1", uniqueID="TT-1")
    locker = SimpleNamespace(key=locker_key) if locker_key is not None else None
    theme.spec = SimpleNamespace(key="s1", locker=locker)
    return theme


def _requirement(extended_id: str = "ER_WHY299") -> RequirementAssignment:
    return RequirementAssignment(
        key="473",
        name="Automatic discount",
        id=extended_id,
        extendedId=extended_id,
        version="1",
        owner="someone",
        status="open",
        priority="high",
        repositoryId="MS Excel",
    )


class _Recorder:
    """Records which write-back patches were applied, in order."""

    def __init__(self):
        self.calls: list[str] = []
        self.failing: set[str] = set()

    def hook(self, label: str):
        async def _patch(*_args, **_kwargs):
            self.calls.append(label)
            if label in self.failing:
                raise RuntimeError(f"{label} failed")

        return _patch


@pytest.fixture
def wired(monkeypatch):
    """Wire the agent's collaborators to fakes and return the control surface."""
    recorder = _Recorder()
    state = SimpleNamespace(
        recorder=recorder,
        theme=_theme_node(),
        requirements=[_requirement()],
        load_error=None,
        ai_result="1 Test case: Discount of 0%",
        ai_error=None,
        ai_calls=[],
    )

    def _structure(**_kwargs):
        return SimpleNamespace(root=state.theme, nodes=[])

    async def _load(*_args, **_kwargs):
        if state.load_error is not None:
            raise state.load_error
        return state.requirements

    async def _ai(self, llm_client, llm_config, prompt_config, agent_data=None):
        state.ai_calls.append(agent_data)
        if state.ai_error is not None:
            raise state.ai_error
        return SimpleNamespace(result=state.ai_result)

    monkeypatch.setattr(agent_module, "post_project_tov_structure", _structure)
    monkeypatch.setattr(
        agent_module,
        "get_test_theme_details",
        lambda **_kwargs: SimpleNamespace(spec=SimpleNamespace(description="Old")),
    )
    monkeypatch.setattr(agent_module, "load_requirements", _load)
    monkeypatch.setattr(agent_module, "patch_generation_started", recorder.hook("started"))
    monkeypatch.setattr(agent_module, "patch_generated_test_ideas", recorder.hook("generated"))
    monkeypatch.setattr(agent_module, "patch_generation_failed", recorder.hook("failed"))
    monkeypatch.setattr(RequirementAgent, "get_ai_response", _ai)
    return state


async def _run(context=None):
    await RequirementAgent().run(context or _context(), MagicMock(), MagicMock(), [])


class TestPrecheck:
    async def test_passes_without_gating_anything(self):
        result = await RequirementAgent().precheck(_context(), MagicMock())

        assert result.passed is True
        assert result.items == []


class TestHappyPath:
    async def test_patches_started_then_the_generated_ideas(self, wired):
        await _run()

        assert wired.recorder.calls == ["started", "generated"]

    async def test_asks_once_for_all_loaded_requirements(self, wired):
        wired.requirements = [_requirement("ER_1"), _requirement("ER_2")]

        await _run()

        (agent_data,) = wired.ai_calls
        assert len(agent_data["requirements"]) == 2
        assert "ER_1" in agent_data["requirements"][0]
        assert "Test theme: Discounts" in agent_data["existing_tests"]


class TestNothingToDo:
    async def test_writes_nothing_when_the_root_is_not_a_test_theme(self, wired):
        wired.theme = SimpleNamespace(base=SimpleNamespace(key="k"))

        await _run()

        assert wired.recorder.calls == []
        assert wired.ai_calls == []

    async def test_writes_nothing_when_the_requirements_cannot_be_loaded(self, wired):
        wired.load_error = RuntimeError("404")

        await _run()

        assert wired.recorder.calls == []

    async def test_writes_nothing_when_no_requirements_are_assigned(self, wired):
        wired.requirements = []

        await _run()

        assert wired.recorder.calls == []
        assert wired.ai_calls == []

    async def test_skips_a_theme_locked_by_another_user(self, wired):
        wired.theme = _theme_node(locker_key="someone-else")

        await _run()

        assert wired.recorder.calls == []

    async def test_still_writes_a_theme_locked_by_the_triggering_user(self, wired):
        wired.theme = _theme_node(locker_key="u1")

        await _run()

        assert wired.recorder.calls == ["started", "generated"]


class TestFailureHandling:
    async def test_rolls_back_when_generation_fails(self, wired):
        wired.ai_error = RuntimeError("upstream refused")

        await _run()

        assert wired.recorder.calls == ["started", "failed"]

    async def test_rolls_back_when_writing_the_ideas_fails(self, wired):
        wired.recorder.failing = {"generated"}

        await _run()

        assert wired.recorder.calls == ["started", "generated", "failed"]

    async def test_a_failing_rollback_does_not_escape_the_run(self, wired):
        wired.ai_error = RuntimeError("upstream refused")
        wired.recorder.failing = {"failed"}

        await _run()

        assert wired.recorder.calls == ["started", "failed"]
