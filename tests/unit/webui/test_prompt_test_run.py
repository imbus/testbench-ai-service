import asyncio

import pytest
from fastapi import HTTPException

from testbench_ai_service.webui.models import RenderedMessage
from testbench_ai_service.webui.prompt_test import (
    PROMPT_TEST_TIMEOUT,
    RunOutcome,
    SingleFlight,
    run_query,
    scrub,
    scrub_all,
    to_messages,
)


class TestSingleFlight:
    def test_a_free_key_is_admitted(self):
        flight = SingleFlight()
        with flight.hold("sid-1"):
            pass

    def test_a_held_key_is_refused_with_409(self):
        flight = SingleFlight()
        with (
            flight.hold("sid-1"),
            pytest.raises(HTTPException) as excinfo,
            flight.hold("sid-1"),
        ):
            pass
        assert excinfo.value.status_code == 409

    def test_a_different_key_is_unaffected(self):
        # Per session, not per process: the lock stops a stuck UI repeating,
        # it does not serialise the organisation (design 9).
        flight = SingleFlight()
        with flight.hold("sid-1"), flight.hold("sid-2"):
            pass

    def test_the_key_is_released_after_a_raise(self):
        flight = SingleFlight()
        with pytest.raises(RuntimeError), flight.hold("sid-1"):
            raise RuntimeError("boom")
        with flight.hold("sid-1"):
            pass


class TestScrub:
    def test_replaces_every_occurrence_of_the_credential(self):
        assert scrub("bad key sk-abc and sk-abc", "sk-abc") == "bad key *** and ***"

    def test_leaves_the_message_alone_when_there_is_no_credential(self):
        assert scrub("model not found", None) == "model not found"

    def test_an_empty_credential_is_not_treated_as_a_match(self):
        assert scrub("model not found", "") == "model not found"

    def test_unrelated_text_survives(self):
        assert scrub("404 model not found", "sk-abc") == "404 model not found"


class TestScrubAll:
    def test_masks_every_candidate_credential(self):
        # A project run may have used either key; both must be masked.
        message = "global sk-global project sk-project"
        assert scrub_all(message, ["sk-global", "sk-project"]) == "global *** project ***"

    def test_skips_absent_candidates(self):
        assert scrub_all("bad key sk-global", ["sk-global", None]) == "bad key ***"

    def test_an_empty_candidate_list_leaves_the_message_alone(self):
        assert scrub_all("model not found", []) == "model not found"


class TestToMessages:
    def test_maps_role_and_content(self):
        rendered = [RenderedMessage(role="system", content="hello", error=None)]
        assert [(m.role, m.content) for m in to_messages(rendered)] == [("system", "hello")]


class TestRunQuery:
    @pytest.mark.asyncio
    async def test_returns_text_and_a_latency(self):
        class FakeClient:
            async def query_llm(self, model, messages, **kwargs):
                return "the answer"

        outcome = await run_query(FakeClient(), "claude-opus-5", [])

        assert isinstance(outcome, RunOutcome)
        assert outcome.text == "the answer"
        assert outcome.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_a_slow_call_times_out(self):
        class SlowClient:
            async def query_llm(self, model, messages, **kwargs):
                await asyncio.sleep(5)
                return "never"

        with pytest.raises(HTTPException) as excinfo:
            await run_query(SlowClient(), "claude-opus-5", [], timeout=0.01)

        assert excinfo.value.status_code == 504
        assert "0.01" in str(excinfo.value.detail)

    def test_the_default_timeout_is_a_bounded_number(self):
        assert 0 < PROMPT_TEST_TIMEOUT <= 300
