"""Tests for the requirement agent's orchestration and write-back sequence."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from testbench_ai_service.agents.requirement import agent as agent_module
from testbench_ai_service.agents.requirement.agent import RequirementAgent
from testbench_ai_service.agents.requirement.model import ThemeContext
from testbench_ai_service.models.language import LanguageOption


def _context(root_uid: str = "ER_WHY299", user_key: str = "u1") -> SimpleNamespace:
    return SimpleNamespace(
        user_key=user_key,
        project_name="VSR-Dreamcar",
        project_key="10004",
        tov_key="42",
        cycle_key=None,
        root_uid=root_uid,
        language=LanguageOption.ENGLISH,
        llm_config=SimpleNamespace(model="gpt-4.1-mini", model_extra={}),
        prompt_config=SimpleNamespace(file="requirement/prompt.yaml", variant="Default"),
        templates_dir=Path("templates"),
    )


def _theme_node(name: str = "Discounts", spec_key: str = "s1", locker_key: str | None = None):
    locker = SimpleNamespace(key=locker_key) if locker_key is not None else None
    return SimpleNamespace(
        base=SimpleNamespace(name=name, key=f"k-{spec_key}", uniqueID=f"TT-{spec_key}"),
        spec=SimpleNamespace(key=spec_key, locker=locker),
    )


def _theme_context(name: str = "Discounts", description: str = "<html><body>Old</body></html>"):
    return ThemeContext(theme_name=name, description=description)


class _Recorder:
    """Records which write-back patches were applied, in order."""

    def __init__(self, failing: set[str] | None = None):
        self.calls: list[tuple[str, str]] = []
        self._failing = failing or set()

    def hook(self, label: str):
        async def _patch(*_args, spec_key: str, **_kwargs):
            self.calls.append((label, spec_key))
            if f"{label}:{spec_key}" in self._failing:
                raise RuntimeError(f"{label} failed for {spec_key}")

        return _patch

    def labels(self, spec_key: str) -> list[str]:
        return [label for label, key in self.calls if key == spec_key]


@pytest.fixture
def wired(monkeypatch, baseline):
    """Wire the agent's collaborators to fakes and return the control surface."""
    recorder = _Recorder()
    state = SimpleNamespace(
        recorder=recorder,
        theme_contexts=[(_theme_node(), _theme_context())],
        ai_result="1. Try a discount of 0%.",
        ai_error=None,
        baseline_error=None,
        loaded=[],
        ai_calls=[],
    )

    async def _load(conn, tov_key, **kwargs):
        state.loaded.append(tov_key)
        if state.baseline_error is not None:
            raise state.baseline_error
        return baseline

    async def _collect(conn, **kwargs):
        return state.theme_contexts

    async def _ai(self, llm_client, llm_config, prompt_config, agent_data=None):
        state.ai_calls.append(agent_data)
        if state.ai_error is not None:
            raise state.ai_error
        return SimpleNamespace(result=state.ai_result)

    monkeypatch.setattr(agent_module, "load_current_baseline", _load)
    monkeypatch.setattr(agent_module, "collect_theme_contexts", _collect)
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

        assert wired.recorder.labels("s1") == ["started", "generated"]

    async def test_processes_every_linked_theme(self, wired):
        wired.theme_contexts = [
            (_theme_node("Discounts", "s1"), _theme_context("Discounts")),
            (_theme_node("Pricing", "s2"), _theme_context("Pricing")),
        ]

        await _run()

        assert wired.recorder.labels("s1") == ["started", "generated"]
        assert wired.recorder.labels("s2") == ["started", "generated"]


class TestNothingToDo:
    async def test_writes_nothing_when_the_requirement_cannot_be_resolved(self, wired):
        await _run(_context(root_uid="ER_NOPE999"))

        assert wired.recorder.calls == []

    async def test_does_not_load_a_baseline_without_a_root_uid(self, wired):
        await _run(_context(root_uid=None))

        assert wired.loaded == []
        assert wired.recorder.calls == []

    async def test_writes_nothing_when_the_baseline_cannot_be_loaded(self, wired):
        wired.baseline_error = RuntimeError("no CURRENT baseline")

        await _run()

        assert wired.recorder.calls == []

    async def test_skips_a_theme_locked_by_another_user(self, wired):
        wired.theme_contexts = [
            (_theme_node("Discounts", "s1", locker_key="someone-else"), _theme_context()),
        ]

        await _run()

        assert wired.recorder.calls == []

    async def test_still_writes_a_theme_locked_by_the_triggering_user(self, wired):
        wired.theme_contexts = [
            (_theme_node("Discounts", "s1", locker_key="u1"), _theme_context()),
        ]

        await _run()

        assert wired.recorder.labels("s1") == ["started", "generated"]


class TestFailureHandling:
    async def test_rolls_back_when_generation_fails(self, wired):
        wired.ai_error = RuntimeError("upstream refused")

        await _run()

        assert wired.recorder.labels("s1") == ["started", "failed"]

    async def test_one_theme_failing_does_not_stop_the_others(self, wired):
        wired.theme_contexts = [
            (_theme_node("Discounts", "s1"), _theme_context("Discounts")),
            (_theme_node("Pricing", "s2"), _theme_context("Pricing")),
        ]
        wired.recorder._failing = {"generated:s1"}

        await _run()

        assert wired.recorder.labels("s1") == ["started", "generated", "failed"]
        assert wired.recorder.labels("s2") == ["started", "generated"]

    async def test_a_failing_rollback_does_not_escape_the_run(self, wired):
        wired.ai_error = RuntimeError("upstream refused")
        wired.recorder._failing = {"failed:s1"}

        await _run()

        assert wired.recorder.labels("s1") == ["started", "failed"]


class TestUnlinkedRequirement:
    """A requirement no theme links still gets ideas; they are logged, not written."""

    async def test_asks_the_ai_even_when_no_theme_links_the_requirement(self, wired):
        wired.theme_contexts = []

        await _run()

        assert len(wired.ai_calls) == 1

    async def test_assembles_the_context_without_the_theme_tiers(self, wired):
        wired.theme_contexts = []

        await _run()

        (agent_data,) = wired.ai_calls
        assert agent_data["existing_tests"] == ""
        assert agent_data["related_tests"] == ""
        assert "ER_WHY299" in agent_data["requirement"]

    async def test_writes_nothing_when_no_theme_links_the_requirement(self, wired):
        wired.theme_contexts = []

        await _run()

        assert wired.recorder.calls == []

    async def test_logs_the_generated_ideas_when_no_theme_links_the_requirement(
        self, wired, caplog
    ):
        """With nowhere to write, the log is the only place the ideas survive."""
        wired.theme_contexts = []

        with caplog.at_level("INFO", logger="testbench_ai_service"):
            await _run()

        assert "No test theme links requirement" in caplog.text
        assert "ER_WHY299" in caplog.text
        assert wired.ai_result in caplog.text

    async def test_logs_an_error_when_generation_fails_without_a_theme(self, wired, caplog):
        wired.theme_contexts = []
        wired.ai_error = RuntimeError("model unavailable")

        with caplog.at_level("ERROR", logger="testbench_ai_service"):
            await _run()

        assert "model unavailable" in caplog.text
        assert wired.recorder.calls == []
