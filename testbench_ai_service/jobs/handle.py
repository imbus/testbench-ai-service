"""The job an agent run belongs to, reached through a ContextVar.

Agents call ``current_job()`` and report progress, warnings and their report
without knowing whether a job exists: outside a job scope they get a handle
that does nothing. Writes go through ``JobStore``, which logs and drops
failures, so a broken job file never fails the run.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from pydantic import BaseModel

from testbench_ai_service.jobs.store import JobStore


class JobHandle:
    """Write access to one job."""

    def __init__(self, job_id: str, store: JobStore) -> None:
        self.job_id = job_id
        self._store = store
        self._failed = False

    @property
    def failed(self) -> bool:
        return self._failed

    async def progress(self, done: int, total: int, text: str | None = None) -> None:
        await self._store.run(self._store.progress, self.job_id, done, total, text)

    async def set_report(self, report_type: str, report: BaseModel | dict[str, Any]) -> None:
        data = report.model_dump(mode="json") if isinstance(report, BaseModel) else report
        await self._store.run(self._store.set_report, self.job_id, report_type, data)

    async def warn(self, message: str) -> None:
        await self._store.run(self._store.add_warning, self.job_id, message)

    async def fail(self, message: str) -> None:
        """End the job as failed; the first outcome of a job is the one that stays."""
        self._failed = True
        await self._store.run(self._store.finish, self.job_id, "failed", message)


class NullJobHandle:
    """Stands in when no job is tracked; every call is a no-op."""

    job_id = ""
    failed = False

    async def progress(self, done: int, total: int, text: str | None = None) -> None:
        return None

    async def set_report(self, report_type: str, report: BaseModel | dict[str, Any]) -> None:
        return None

    async def warn(self, message: str) -> None:
        return None

    async def fail(self, message: str) -> None:
        return None


_NULL = NullJobHandle()
_current_job: ContextVar[JobHandle | None] = ContextVar("current_job", default=None)


def current_job() -> JobHandle | NullJobHandle:
    """The job of the running agent, or a handle that does nothing."""
    return _current_job.get() or _NULL


@contextmanager
def job_scope(handle: JobHandle) -> Iterator[None]:
    """Make *handle* the current job inside the block."""
    token = _current_job.set(handle)
    try:
        yield
    finally:
        _current_job.reset(token)
