import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from testbench_ai_service.llm.base import LLMProvider, LLMResult, TokenUsage
from testbench_ai_service.models.prompt import Message
from testbench_ai_service.tasks import run_agent
from testbench_ai_service.usage import (
    USAGE_FILE_NAME,
    UsageRecordingClient,
    UsageStore,
    resolve_usage_file,
)

MESSAGES = [Message(role="user", content="q")]


@pytest.fixture
def store(tmp_path) -> UsageStore:
    return UsageStore(tmp_path / "usage.sqlite")


class TestResolveUsageFile:
    def test_unset_means_next_to_the_config_file(self, tmp_path):
        config = tmp_path / "conf" / "config.toml"
        assert resolve_usage_file(None, config) == tmp_path / "conf" / USAGE_FILE_NAME

    def test_a_relative_path_is_resolved_against_the_config_directory(self, tmp_path):
        config = tmp_path / "conf" / "config.toml"
        assert resolve_usage_file(Path("data/u.db"), config) == tmp_path / "conf" / "data/u.db"

    def test_an_absolute_path_is_kept(self, tmp_path):
        target = tmp_path / "elsewhere" / "u.db"
        assert resolve_usage_file(target, tmp_path / "config.toml") == target


class TestUsageStore:
    def test_an_unused_store_reports_nothing(self, store):
        assert store.totals() == []

    def test_calls_on_one_model_add_up_in_one_row(self, store):
        store.record("anthropic", "claude-opus-5", TokenUsage(10, 20, 5))
        store.record("anthropic", "claude-opus-5", TokenUsage(1, 2, None))

        [row] = store.totals()
        assert (row.calls, row.input_tokens, row.output_tokens, row.reasoning_tokens) == (
            2,
            11,
            22,
            5,
        )

    def test_a_call_without_usage_counts_as_a_call_only(self, store):
        store.record("custom", "my-model", None)

        [row] = store.totals()
        assert (row.calls, row.input_tokens, row.output_tokens) == (1, 0, 0)

    def test_the_same_model_name_under_two_providers_stays_apart(self, store):
        store.record("openai", "gpt-5", TokenUsage(1, 1))
        store.record("azure_openai", "gpt-5", TokenUsage(1, 1))

        assert {(row.provider, row.model) for row in store.totals()} == {
            ("openai", "gpt-5"),
            ("azure_openai", "gpt-5"),
        }

    def test_the_largest_consumer_comes_first(self, store):
        store.record("openai", "small", TokenUsage(1, 1))
        store.record("openai", "big", TokenUsage(100, 100))

        assert [row.model for row in store.totals()] == ["big", "small"]

    def test_totals_survive_a_new_store_on_the_same_file(self, store):
        # What "kept across restarts" means: a fresh process opens the file.
        store.record("openai", "gpt-5", TokenUsage(3, 4))
        assert UsageStore(store.path).totals()[0].input_tokens == 3

    def test_the_parent_directory_is_created(self, tmp_path):
        nested = UsageStore(tmp_path / "a" / "b" / "usage.sqlite")
        nested.record("openai", "gpt-5", TokenUsage(1, 1))
        assert nested.path.exists()

    def test_a_failed_write_is_logged_not_raised(self, tmp_path, caplog):
        # A directory where the file should be: sqlite cannot open it.
        (tmp_path / "usage.sqlite").mkdir()
        UsageStore(tmp_path / "usage.sqlite").record("openai", "gpt-5", TokenUsage(1, 1))
        assert "Could not record token usage" in caplog.text

    def test_a_failed_read_raises_for_the_caller_to_report(self, tmp_path):
        (tmp_path / "usage.sqlite").mkdir()
        with pytest.raises(sqlite3.Error):
            UsageStore(tmp_path / "usage.sqlite").totals()


class TestUsageRecordingClient:
    def _inner(self, result=None, error=None) -> MagicMock:
        inner = MagicMock()
        inner.query_llm_with_usage = AsyncMock(
            return_value=result or LLMResult(text="hi", usage=TokenUsage(7, 8)),
            side_effect=error,
        )
        return inner

    @pytest.mark.asyncio
    async def test_a_call_is_recorded_under_the_provider_and_model(self, store):
        client = UsageRecordingClient(self._inner(), store, "anthropic")

        assert await client.query_llm("claude-opus-5", MESSAGES) == "hi"

        [row] = store.totals()
        assert (row.provider, row.model, row.input_tokens, row.output_tokens) == (
            "anthropic",
            "claude-opus-5",
            7,
            8,
        )

    @pytest.mark.asyncio
    async def test_the_result_passes_through_unchanged(self, store):
        result = LLMResult(text="hi", usage=TokenUsage(1, 2, 1))
        client = UsageRecordingClient(self._inner(result), store, "openai")

        assert await client.query_llm_with_usage("o3", MESSAGES) == result

    @pytest.mark.asyncio
    async def test_a_failed_call_is_not_recorded(self, store):
        client = UsageRecordingClient(self._inner(error=RuntimeError("down")), store, "openai")

        with pytest.raises(RuntimeError):
            await client.query_llm("gpt-5", MESSAGES)

        assert store.totals() == []

    @pytest.mark.asyncio
    async def test_close_leaves_the_shared_client_open(self, store):
        # The factory caches and owns the inner client; closing a wrapper
        # after one run must not break the next run that reuses it.
        inner = self._inner()
        inner.close = AsyncMock()
        await UsageRecordingClient(inner, store, "openai").close()
        inner.close.assert_not_awaited()

    def test_other_attributes_reach_the_inner_client(self, store):
        inner = self._inner()
        inner.custom_feature = "yes"
        assert UsageRecordingClient(inner, store, "custom").custom_feature == "yes"


class TestRunAgentCountsUsage:
    async def _run(self, usage_store):
        inner = MagicMock()
        inner.query_llm_with_usage = AsyncMock(
            return_value=LLMResult(text="x", usage=TokenUsage(5, 6))
        )
        factory = MagicMock()
        factory.get_client.return_value = inner
        factory.resolve_provider.return_value = LLMProvider.OPENAI

        async def agent_run(context, conn, llm_client, item_ids):
            await llm_client.query_llm(model="gpt-5", messages=MESSAGES)

        agent = MagicMock()
        agent.run = agent_run
        with patch("testbench_ai_service.tasks.get_prompt_model", return_value="gpt-5"):
            await run_agent(
                agent_key="k",
                agent=agent,
                context=MagicMock(user_key="u", project_key="p", project_name="P"),
                conn=MagicMock(),
                llm_factory=factory,
                item_ids=["1"],
                usage_store=usage_store,
            )

    @pytest.mark.asyncio
    async def test_an_agent_run_is_counted_under_the_resolved_provider(self, store):
        await self._run(store)

        [row] = store.totals()
        assert (row.provider, row.model, row.input_tokens, row.output_tokens) == (
            "openai",
            "gpt-5",
            5,
            6,
        )

    @pytest.mark.asyncio
    async def test_without_a_store_the_run_still_works(self):
        await self._run(None)
