"""How many agent runs are in flight.

Agent executions are dispatched as FastAPI background tasks, which the
framework does not track. Before the console reloads the configuration under a
running service, the operator deserves to know whether anything is mid-flight
-- a reload that swaps the LLM clients out from under a running agent is
recoverable, but it is not a surprise anyone wants.

The registry is deliberately a counter with labels, not a task manager: it
never cancels, joins or owns anything. Being wrong about the count is the worst
it can do, and the ``finally`` in :meth:`TaskRegistry.track` is what keeps even
that from happening.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Request


class TaskRegistry:
    """A count of the agent runs currently executing in this process."""

    def __init__(self) -> None:
        self._labels: list[str] = []

    @property
    def count(self) -> int:
        return len(self._labels)

    def labels(self) -> list[str]:
        """The agent key of each in-flight run, in the order they started.

        Duplicates are real: two concurrent runs of the same agent are two
        entries.
        """
        return list(self._labels)

    @asynccontextmanager
    async def track(self, label: str) -> AsyncIterator[None]:
        """Count one run of *label* for the duration of the block.

        The decrement is in a ``finally``: an agent that raises must not leave
        a phantom count behind, or the console would report an in-flight task
        forever.
        """
        self._labels.append(label)
        try:
            yield
        finally:
            # remove(), not pop(): concurrent runs finish out of order.
            self._labels.remove(label)


def get_task_registry(request: Request) -> TaskRegistry:
    """FastAPI dependency: the process's task registry."""
    registry: TaskRegistry = request.app.state.task_registry
    return registry
