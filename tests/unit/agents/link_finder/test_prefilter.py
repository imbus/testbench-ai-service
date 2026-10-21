"""Stage 1: screening every unlinked set by title, path and short description."""

from testbench_ai_service.agents.link_finder.model import (
    PrefilterAnswer,
    PrefilterHit,
    TestCaseSetSummary,
)
from testbench_ai_service.agents.link_finder.prefilter import (
    SHORT_DESCRIPTION_LENGTH,
    LlmPrefilter,
    render_summaries,
    summarize,
    validate_hits,
)
from testbench_ai_service.utils.structured_output import StructuredOutputError
from testbench_ai_service.utils.traceability.models import Aspect
from tests.unit.utils.traceability.fakes import test_case_set

ASPECTS = [Aspect(id="A1", statement="Lock after 3 failures", kind="boundary", source_quote="q")]


def _summary(key, path=None):
    return TestCaseSetSummary(
        key=key, title=f"Set {key}", path=path or f"/{key}", description_short="", spec_status="R"
    )


def _hit(key, relevance="medium"):
    return PrefilterHit(set_key=key, relevance=relevance, reason="r")


class TestSummarize:
    def test_only_the_wanted_sets_sorted_by_path(self):
        catalog = {
            "b": test_case_set("b", "/B"),
            "a": test_case_set("a", "/A"),
            "x": test_case_set("x", "/X"),
        }

        assert [s.key for s in summarize(catalog, ["b", "a"])] == ["a", "b"]

    def test_the_description_is_visible_text_and_shortened(self):
        long = "word " * 200
        catalog = {"a": test_case_set("a", "/A", description=f"<p>{long}</p>")}

        (summary,) = summarize(catalog, ["a"])

        assert "<p>" not in summary.description_short
        assert summary.description_short.endswith(" ...")
        assert len(summary.description_short) <= SHORT_DESCRIPTION_LENGTH + 4


def test_render_summaries():
    summary = _summary("a", "/Auth/Lock")

    assert render_summaries([summary]) == "a | /Auth/Lock | Set a | -"


class TestValidateHits:
    def test_unknown_keys_are_dropped_and_keys_trimmed(self):
        hits = validate_hits([_hit(" a "), _hit("ghost")], [_summary("a")], 15)

        assert [h.set_key for h in hits] == ["a"]

    def test_a_repeated_key_keeps_its_highest_relevance(self):
        hits = validate_hits([_hit("a", "low"), _hit("a", "high")], [_summary("a")], 15)

        assert [(h.set_key, h.relevance) for h in hits] == [("a", "high")]

    def test_the_cap_keeps_the_most_relevant_in_path_order(self):
        sets = [_summary(key) for key in "abcd"]
        hits = [_hit("d", "high"), _hit("a", "low"), _hit("c", "medium"), _hit("b", "medium")]

        assert [h.set_key for h in validate_hits(hits, sets, 3)] == ["d", "b", "c"]


async def test_the_sets_are_screened_in_batches():
    calls = []

    async def ask(step, schema, agent_data):
        keys = [line.split(" | ")[0] for line in agent_data["test_case_sets"].splitlines()]
        calls.append((step, keys))
        return PrefilterAnswer(hits=[_hit(keys[0])])

    sets = [_summary(key) for key in "abcde"]

    result = await LlmPrefilter(ask, batch_size=2, max_candidates=15, max_parallel=2).run(
        "REQ-42: Login", ASPECTS, sets
    )

    assert sorted(calls) == [
        ("prefilter", ["a", "b"]),
        ("prefilter", ["c", "d"]),
        ("prefilter", ["e"]),
    ]
    assert [h.set_key for h in result.hits] == ["a", "c", "e"]
    assert (result.sets_screened, result.incomplete) == (5, False)


async def test_a_failing_batch_loses_only_its_sets():
    async def ask(step, schema, agent_data):
        if agent_data["test_case_sets"].startswith("c"):
            raise StructuredOutputError("bad", raw_response="?")
        return PrefilterAnswer(hits=[_hit("a")])

    sets = [_summary(key) for key in "abcd"]

    result = await LlmPrefilter(ask, batch_size=2, max_candidates=15, max_parallel=1).run(
        "REQ-42", ASPECTS, sets
    )

    assert [h.set_key for h in result.hits] == ["a"]
    assert result.incomplete is True
