"""Token consumption per model, kept across restarts in a SQLite file.

Only running totals are stored -- one row per (provider, model), never one
row per call. The question this answers is "which model has used how many
tokens", not "who ran what when".

Counting is an observer: a write that fails is logged and dropped, never
raised, because a broken usage file must not fail an agent run that already
paid for its LLM call.
"""

import asyncio
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Request

from testbench_ai_service.llm.base import LLMClient, LLMResult, TokenUsage
from testbench_ai_service.log import logger
from testbench_ai_service.models.prompt import Message

#: The file name used when ``usage_file`` is not configured.
USAGE_FILE_NAME = "usage.sqlite"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS model_usage (
    provider         TEXT    NOT NULL,
    model            TEXT    NOT NULL,
    calls            INTEGER NOT NULL DEFAULT 0,
    input_tokens     INTEGER NOT NULL DEFAULT 0,
    output_tokens    INTEGER NOT NULL DEFAULT 0,
    reasoning_tokens INTEGER NOT NULL DEFAULT 0,
    last_used        TEXT    NOT NULL,
    PRIMARY KEY (provider, model)
)
"""

# One statement, so concurrent writers -- other coroutines' threads, or a
# second worker process on the same file -- cannot lose an increment.
_UPSERT = """
INSERT INTO model_usage
    (provider, model, calls, input_tokens, output_tokens, reasoning_tokens, last_used)
VALUES (?, ?, 1, ?, ?, ?, ?)
ON CONFLICT (provider, model) DO UPDATE SET
    calls            = calls + 1,
    input_tokens     = input_tokens + excluded.input_tokens,
    output_tokens    = output_tokens + excluded.output_tokens,
    reasoning_tokens = reasoning_tokens + excluded.reasoning_tokens,
    last_used        = excluded.last_used
"""

_SELECT = """
SELECT provider, model, calls, input_tokens, output_tokens, reasoning_tokens, last_used
FROM model_usage
ORDER BY input_tokens + output_tokens DESC, model
"""


@dataclass(frozen=True)
class ModelUsage:
    """The running totals for one model."""

    provider: str
    model: str
    calls: int
    input_tokens: int
    output_tokens: int
    #: Part of ``output_tokens``, not on top of it.
    reasoning_tokens: int
    last_used: datetime


def resolve_usage_file(configured: Path | None, config_path: Path) -> Path:
    """Where the usage file lives.

    Unset means next to the config file; a relative path is resolved against
    the config file's directory too, so the location does not depend on the
    working directory the service happened to be started from.
    """
    path = configured if configured is not None else Path(USAGE_FILE_NAME)
    if path.is_absolute():
        return path
    return config_path.resolve().parent / path


class UsageStore:
    """Running token totals per model in a SQLite file.

    A fresh connection per operation: the calls are rare next to the LLM
    requests they count, and it keeps the store safe to use from the worker
    threads ``asyncio.to_thread`` hands it to. The file and its table are
    created on first use, so a path that cannot be written does not stop the
    service from starting.
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=5.0)
        conn.execute(_SCHEMA)
        return conn

    def record(self, provider: str, model: str, usage: TokenUsage | None) -> None:
        """Add one call to *model*'s totals; a call without usage counts as a call only."""
        input_tokens = usage.input_tokens if usage else 0
        output_tokens = usage.output_tokens if usage else 0
        reasoning_tokens = (usage.reasoning_tokens or 0) if usage else 0
        try:
            conn = self._connect()
            try:
                with conn:
                    conn.execute(
                        _UPSERT,
                        (
                            provider,
                            model,
                            input_tokens,
                            output_tokens,
                            reasoning_tokens,
                            datetime.now(timezone.utc).isoformat(),
                        ),
                    )
            finally:
                conn.close()
        except (sqlite3.Error, OSError) as e:
            logger.warning("Could not record token usage in '%s': %r", self.path, e)

    async def record_async(self, provider: str, model: str, usage: TokenUsage | None) -> None:
        """``record`` off the event loop: a SQLite commit waits on the disk."""
        await asyncio.to_thread(self.record, provider, model, usage)

    def totals(self) -> list[ModelUsage]:
        """Every model's totals, largest consumer first.

        Raises ``sqlite3.Error`` or ``OSError`` -- unlike ``record``, a read
        is for display, and the caller decides how to show that it failed.
        """
        conn = self._connect()
        try:
            rows = conn.execute(_SELECT).fetchall()
        finally:
            conn.close()
        return [
            ModelUsage(
                provider=provider,
                model=model,
                calls=calls,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                reasoning_tokens=reasoning_tokens,
                last_used=datetime.fromisoformat(last_used),
            )
            for provider, model, calls, input_tokens, output_tokens, reasoning_tokens, last_used in rows
        ]


class UsageRecordingClient(LLMClient):
    """An LLM client that adds every successful call to a ``UsageStore``.

    Wraps the factory's client at the call site rather than living inside the
    factory: the factory is rebuilt on every config reload, while the store
    lives as long as the process. A failed call is not counted -- whether a
    provider bills a failed request is not something the service can know.
    """

    def __init__(self, inner: LLMClient, store: UsageStore, provider: str) -> None:
        self.inner = inner
        self.store = store
        self.provider = provider

    async def query_llm(self, model: str, messages: list[Message], **kwargs: Any) -> str:
        result = await self.query_llm_with_usage(model=model, messages=messages, **kwargs)
        return result.text

    async def query_llm_with_usage(
        self, model: str, messages: list[Message], **kwargs: Any
    ) -> LLMResult:
        result = await self.inner.query_llm_with_usage(model=model, messages=messages, **kwargs)
        await self.store.record_async(self.provider, model, result.usage)
        return result

    async def close(self) -> None:
        """Nothing to release: the factory owns, caches and closes ``inner``."""

    def __getattr__(self, name: str) -> Any:
        # Only reached for attributes the wrapper lacks. "inner" itself is
        # refused, or a lookup before __init__ sets it would recurse forever.
        if name == "inner":
            raise AttributeError(name)
        # A custom agent may reach for something its own custom client
        # offers beyond the LLMClient interface; wrapping must not take it away.
        return getattr(self.inner, name)


def get_usage_store(request: Request) -> UsageStore:
    """FastAPI dependency: the process's usage store."""
    store: UsageStore = request.app.state.usage_store
    return store
