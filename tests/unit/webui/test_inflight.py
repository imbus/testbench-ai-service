import asyncio

import pytest

from testbench_ai_service.webui.inflight import TaskRegistry


async def test_a_fresh_registry_is_empty():
    registry = TaskRegistry()

    assert registry.count == 0
    assert registry.labels() == []


async def test_a_tracked_task_is_counted_while_it_runs():
    registry = TaskRegistry()
    inside = asyncio.Event()
    release = asyncio.Event()

    async def work():
        async with registry.track("reviewer"):
            inside.set()
            await release.wait()

    task = asyncio.create_task(work())
    await inside.wait()

    assert registry.count == 1
    assert registry.labels() == ["reviewer"]

    release.set()
    await task

    assert registry.count == 0
    assert registry.labels() == []


async def test_concurrent_tasks_are_counted_independently():
    registry = TaskRegistry()
    release = asyncio.Event()

    async def work(label: str):
        async with registry.track(label):
            await release.wait()

    tasks = [asyncio.create_task(work(f"agent_{index}")) for index in range(3)]
    await asyncio.sleep(0)  # let them enter the context manager

    assert registry.count == 3
    assert sorted(registry.labels()) == ["agent_0", "agent_1", "agent_2"]

    release.set()
    await asyncio.gather(*tasks)

    assert registry.count == 0


async def test_a_failing_task_still_decrements():
    """A leaked count would make the restart banner permanent."""
    registry = TaskRegistry()

    with pytest.raises(RuntimeError):
        async with registry.track("reviewer"):
            raise RuntimeError("agent blew up")

    assert registry.count == 0


async def test_the_same_label_twice_is_counted_twice():
    registry = TaskRegistry()
    release = asyncio.Event()

    async def work():
        async with registry.track("reviewer"):
            await release.wait()

    tasks = [asyncio.create_task(work()) for _ in range(2)]
    await asyncio.sleep(0)

    assert registry.count == 2
    assert registry.labels() == ["reviewer", "reviewer"]

    release.set()
    await asyncio.gather(*tasks)
