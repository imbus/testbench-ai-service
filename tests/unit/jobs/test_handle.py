from pydantic import BaseModel

from testbench_ai_service.jobs.handle import JobHandle, current_job, job_scope
from testbench_ai_service.jobs.store import JobStore
from tests.unit.jobs.test_store import _create, store  # noqa: F401


class SomeModel(BaseModel):
    a: int


async def test_current_job_outside_scope_is_null_and_harmless():
    job = current_job()
    await job.progress(1, 2)
    await job.set_report("x", {})
    await job.warn("w")
    await job.fail("f")
    assert job.failed is False


async def test_handle_writes_through_to_store(store: JobStore):  # noqa: F811
    _create(store, "j1", "u1")
    handle = JobHandle("j1", store)
    with job_scope(handle):
        assert current_job() is handle
        await current_job().progress(1, 4, "t")
        await current_job().set_report("coverage_checker", SomeModel(a=1))
        await current_job().warn("careful")
    job = store.get("j1", "u1")
    assert job.report == {"a": 1}
    assert (job.progress.done, job.progress.total) == (1, 4)
    assert "careful" in job.warnings
    assert current_job() is not handle


async def test_fail_marks_handle_and_store(store: JobStore):  # noqa: F811
    _create(store, "j1", "u1")
    handle = JobHandle("j1", store)
    await handle.fail("kaputt")
    assert handle.failed
    assert store.get("j1", "u1").error == "kaputt"
