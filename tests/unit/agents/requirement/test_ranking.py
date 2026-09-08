"""Tests for tier-6 candidate ranking."""

from testbench_ai_service.agents.requirement.ranking import (
    SHORTLIST_SIZE,
    LexicalRanker,
    LlmRerankRanker,
)


class TestLexicalRanker:
    async def test_ranks_candidates_sharing_more_words_with_the_target_higher(
        self, make_requirement
    ):
        target = make_requirement("T", "Automatic discount for dealer")
        candidates = [
            make_requirement("C1", "Unrelated import of basic data"),
            make_requirement("C2", "Dealer discount approval"),
            make_requirement("C3", "Automatic dealer discount limit"),
        ]

        ordered = await LexicalRanker().order(target, candidates)

        assert [node.extendedID for node in ordered] == ["C3", "C2"]

    async def test_drops_candidates_that_share_no_words(self, make_requirement):
        target = make_requirement("T", "Automatic discount")
        candidates = [make_requirement("C1", "File import from host")]

        assert await LexicalRanker().order(target, candidates) == []

    async def test_matches_on_udf_values_not_only_the_name(self, make_requirement):
        target = make_requirement("T", "Price display", udf_values=("Marketing",))
        candidates = [
            make_requirement("C1", "Wholly different", udf_values=("Marketing",)),
        ]

        ordered = await LexicalRanker().order(target, candidates)

        assert [node.extendedID for node in ordered] == ["C1"]

    async def test_matches_case_insensitively(self, make_requirement):
        target = make_requirement("T", "Automatic Discount")
        candidates = [make_requirement("C1", "automatic DISCOUNT rules")]

        ordered = await LexicalRanker().order(target, candidates)

        assert [node.extendedID for node in ordered] == ["C1"]

    async def test_excludes_the_target_from_its_own_ranking(self, make_requirement):
        target = make_requirement("T", "Automatic discount")
        candidates = [target, make_requirement("C1", "Automatic discount elsewhere")]

        ordered = await LexicalRanker().order(target, candidates)

        assert [node.extendedID for node in ordered] == ["C1"]

    async def test_breaks_ties_stably_by_extended_id(self, make_requirement):
        target = make_requirement("T", "discount")
        candidates = [
            make_requirement("C_b", "discount"),
            make_requirement("C_a", "discount"),
            make_requirement("C_c", "discount"),
        ]

        ordered = await LexicalRanker().order(target, candidates)

        assert [node.extendedID for node in ordered] == ["C_a", "C_b", "C_c"]


class _FakeLLM:
    """An LLM client that returns a queued reply, or raises a queued error."""

    def __init__(self, reply: str | None = None, error: Exception | None = None):
        self._reply = reply
        self._error = error
        self.calls: list[list] = []

    async def query_llm(self, model: str, messages: list, *args, **kwargs) -> str:
        self.calls.append(messages)
        if self._error is not None:
            raise self._error
        assert self._reply is not None
        return self._reply

    async def close(self):
        pass


class TestLlmRerankRanker:
    async def _candidates(self, make_requirement):
        return [
            make_requirement("C1", "discount alpha"),
            make_requirement("C2", "discount beta"),
            make_requirement("C3", "discount gamma"),
        ]

    async def test_reorders_the_shortlist_into_the_order_the_model_returns(self, make_requirement):
        target = make_requirement("T", "discount")
        candidates = await self._candidates(make_requirement)
        ranker = LlmRerankRanker(_FakeLLM("C3, C1, C2"), model="gpt-4.1-mini")

        ordered = await ranker.order(target, candidates)

        assert [node.extendedID for node in ordered] == ["C3", "C1", "C2"]

    async def test_keeps_omitted_candidates_after_the_ranked_ones(self, make_requirement):
        target = make_requirement("T", "discount")
        candidates = await self._candidates(make_requirement)
        ranker = LlmRerankRanker(_FakeLLM("C3"), model="gpt-4.1-mini")

        ordered = await ranker.order(target, candidates)

        assert [node.extendedID for node in ordered] == ["C3", "C1", "C2"]

    async def test_ignores_identifiers_that_are_not_in_the_shortlist(self, make_requirement):
        target = make_requirement("T", "discount")
        candidates = await self._candidates(make_requirement)
        ranker = LlmRerankRanker(_FakeLLM("C_HALLUCINATED, C2"), model="gpt-4.1-mini")

        ordered = await ranker.order(target, candidates)

        assert [node.extendedID for node in ordered] == ["C2", "C1", "C3"]

    async def test_falls_back_to_lexical_order_when_the_reply_names_nothing_known(
        self, make_requirement
    ):
        target = make_requirement("T", "discount")
        candidates = await self._candidates(make_requirement)
        ranker = LlmRerankRanker(_FakeLLM("I cannot help with that."), model="gpt-4.1-mini")

        ordered = await ranker.order(target, candidates)

        assert [node.extendedID for node in ordered] == ["C1", "C2", "C3"]

    async def test_falls_back_to_lexical_order_when_the_call_raises(self, make_requirement):
        target = make_requirement("T", "discount")
        candidates = await self._candidates(make_requirement)
        ranker = LlmRerankRanker(
            _FakeLLM(error=TimeoutError("upstream timed out")), model="gpt-4.1-mini"
        )

        ordered = await ranker.order(target, candidates)

        assert [node.extendedID for node in ordered] == ["C1", "C2", "C3"]

    async def test_never_asks_the_model_about_more_than_the_shortlist_size(self, make_requirement):
        target = make_requirement("T", "discount")
        candidates = [
            make_requirement(f"C{index:03d}", "discount") for index in range(SHORTLIST_SIZE + 25)
        ]
        llm = _FakeLLM("C001")
        ranker = LlmRerankRanker(llm, model="gpt-4.1-mini")

        ordered = await ranker.order(target, candidates)

        assert len(ordered) == SHORTLIST_SIZE
        assert llm.calls[0][-1].content.count("- C") == SHORTLIST_SIZE

    async def test_does_not_call_the_model_when_nothing_is_relevant(self, make_requirement):
        target = make_requirement("T", "discount")
        llm = _FakeLLM("anything")
        ranker = LlmRerankRanker(llm, model="gpt-4.1-mini")

        ordered = await ranker.order(target, [make_requirement("C1", "unrelated words")])

        assert ordered == []
        assert llm.calls == []
