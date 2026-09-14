"""The one console action that spends money, and what bounds it.

Three guardrails, each closing a different hole (design D5):

* a single-flight lock per session, so a stuck browser cannot bill twice;
* a timeout this module owns, because the SDK's own wall-clock reaches
  ``timeout x (max_retries + 1)`` and is therefore not a bound;
* a credential scrubber, so a provider error cannot become the first route
  that discloses an environment variable's contents (design D9).

The lock is deliberately NOT ``TaskRegistry``: that registry promises it is a
counter whose worst failure is a wrong count, and a mutex built on it would
turn a wrong count into a session locked out forever (design 3.6).
"""

import asyncio
import time
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from fastapi import HTTPException, status

from testbench_ai_service.models.prompt import Message
from testbench_ai_service.webui.models import RenderedMessage

#: The console's own ceiling on a test run, in seconds.
PROMPT_TEST_TIMEOUT: float = 60.0


@dataclass(frozen=True)
class RunOutcome:
    """What a completed call produced."""

    text: str
    latency_ms: int


class SingleFlight:
    """At most one held key at a time, refusing the second with a 409."""

    def __init__(self) -> None:
        self._held: set[str] = set()

    @contextmanager
    def hold(self, key: str) -> Iterator[None]:
        """Hold *key* for the duration of the block, or refuse.

        The release is in a ``finally``: a raising run must not leave the key
        held, or that session could never test again without a restart.
        """
        if key in self._held:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A test run is already in flight for this session.",
            )
        self._held.add(key)
        try:
            yield
        finally:
            self._held.discard(key)


def scrub(message: str, secret: str | None) -> str:
    """Replace every occurrence of *secret* in *message*.

    Exact substring, never a pattern: a heuristic that tries to recognise
    "things that look like keys" both misses real ones and mangles innocent
    text. An empty or absent secret matches nothing -- ``"".replace`` would
    otherwise splice the mask between every character.
    """
    if not secret:
        return message
    return message.replace(secret, "***")


def scrub_all(message: str, secrets: Iterable[str | None]) -> str:
    """Mask every candidate credential in *message*.

    A run resolves either a project credential or the global one, and the
    console cannot see which the SDK actually sent -- so both are masked
    rather than guessed between (design D9).
    """
    for secret in secrets:
        message = scrub(message, secret)
    return message


def to_messages(rendered: list[RenderedMessage]) -> list[Message]:
    """The rendered preview, as the messages a client accepts."""
    return [Message(role=item.role, content=item.content) for item in rendered]


async def run_query(
    client, model: str, messages: list[Message], timeout: float = PROMPT_TEST_TIMEOUT
) -> RunOutcome:
    """Call *client* under the console's own ceiling.

    ``latency_ms`` is wall-clock around the await, so it includes whatever
    retries the SDK performed -- which is what the operator experiences.
    """
    started = time.perf_counter()
    try:
        text = await asyncio.wait_for(client.query_llm(model=model, messages=messages), timeout)
    # asyncio.TimeoutError is only an alias of the builtin from 3.11 on, and
    # pyproject declares support back to 3.10 -- catch both.
    except (asyncio.TimeoutError, TimeoutError) as e:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"The model did not answer within {timeout} seconds.",
        ) from e
    return RunOutcome(text=text, latency_ms=int((time.perf_counter() - started) * 1000))
