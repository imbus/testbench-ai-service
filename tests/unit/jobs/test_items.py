import asyncio

import pytest

from testbench_ai_service.jobs.handle import JobHandle, job_scope
from testbench_ai_service.jobs.items import gather_items
from testbench_ai_service.jobs.store import JobStore
from testbench_ai_service.models.language import LanguageOption
from testbench_ai_service.utils.i18n import load_translations
from tests.unit.jobs.test_store import _create, store  # noqa: F401

load_translations()


async def _ok() -> None:
    return None


async def _boom(text: str = "boom") -> None:
    raise RuntimeError(text)


async def test_one_failing_item_keeps_job_running_with_warning(store: JobStore):  # noqa: F811
    _create(store, "j1", "u1")
    with job_scope(JobHandle("j1", store)):
        await gather_items([("A", _ok()), ("B", _boom())], LanguageOption.ENGLISH)
    job = store.get("j1", "u1")
    assert job.status == "running"
    # The message, not the Python expression RuntimeError('boom').
    assert job.warnings[-1] == "B: processing failed (boom)"


async def test_all_failing_fails_the_job(store: JobStore):  # noqa: F811
    _create(store, "j1", "u1")
    with job_scope(JobHandle("j1", store)):
        await gather_items([("A", _boom()), ("B", _boom())], LanguageOption.GERMAN)
    job = store.get("j1", "u1")
    assert job.status == "failed"
    assert job.error == "Keines der 2 Elemente konnte verarbeitet werden."
    assert job.warnings[-2].startswith("A: Verarbeitung fehlgeschlagen")


async def test_error_text_is_cut(store: JobStore):  # noqa: F811
    _create(store, "j1", "u1")
    with job_scope(JobHandle("j1", store)):
        await gather_items([("A", _boom("x" * 500)), ("B", _ok())], LanguageOption.ENGLISH)
    warning = store.get("j1", "u1").warnings[-1]
    assert len(warning) == len("A: processing failed ()") + 200


async def test_no_items_does_nothing(store: JobStore):  # noqa: F811
    _create(store, "j1", "u1")
    with job_scope(JobHandle("j1", store)):
        await gather_items([], LanguageOption.ENGLISH)
    assert store.get("j1", "u1").status == "running"


async def test_outside_a_job_failures_are_swallowed():
    await gather_items([("A", _boom())], LanguageOption.ENGLISH)


async def test_cancellation_is_not_swallowed():
    async def cancelled() -> None:
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await gather_items([("A", cancelled())], LanguageOption.ENGLISH)
