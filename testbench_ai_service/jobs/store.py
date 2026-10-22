"""Agent jobs kept across restarts in the SQLite file the usage totals use.

Writes are observers like in ``UsageStore``: a failed write is logged and
dropped, never raised, because a broken job file must not fail an agent run.
Reads raise, the caller decides how to show that. The engine, the file and
the table are created on first use, so a path that cannot be written does
not stop the service from starting.
"""

import asyncio
import json
import threading
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal, TypeVar

import sqlalchemy as sa
from fastapi import Request
from sqlalchemy.engine import Engine, Row
from sqlalchemy.exc import SQLAlchemyError

from testbench_ai_service.jobs.models import JobDetail, JobProgress, JobStatus, JobSummary
from testbench_ai_service.log import logger

T = TypeVar("T")

_metadata = sa.MetaData()

# Times are ISO strings in UTC with fixed microseconds, so they sort and
# compare correctly as text.
_jobs = sa.Table(
    "agent_jobs",
    _metadata,
    sa.Column("id", sa.String, primary_key=True),
    sa.Column("agent_key", sa.String, nullable=False),
    sa.Column("user_key", sa.String, nullable=False, index=True),
    sa.Column("project_key", sa.String, nullable=False),
    sa.Column("project_name", sa.String, nullable=False),
    sa.Column("root_key", sa.String, nullable=True),
    sa.Column("item_ids", sa.JSON, nullable=False),
    sa.Column("status", sa.String, nullable=False),
    sa.Column("error", sa.String, nullable=True),
    sa.Column("progress_done", sa.Integer, nullable=True),
    sa.Column("progress_total", sa.Integer, nullable=True),
    sa.Column("progress_text", sa.String, nullable=True),
    sa.Column("warnings", sa.JSON, nullable=False),
    sa.Column("report_type", sa.String, nullable=True),
    sa.Column("report", sa.JSON, nullable=True),
    sa.Column("created_at", sa.String, nullable=False),
    sa.Column("updated_at", sa.String, nullable=False),
    sa.Column("finished_at", sa.String, nullable=True),
)

_SUMMARY_COLUMNS = [c for c in _jobs.c if c.name != "report"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _summary_fields(row: Row[Any]) -> dict[str, Any]:
    progress = None
    if row.progress_done is not None and row.progress_total is not None:
        progress = JobProgress(
            done=row.progress_done, total=row.progress_total, text=row.progress_text
        )
    return {
        "job_id": row.id,
        "agent_key": row.agent_key,
        "project_key": row.project_key,
        "project_name": row.project_name,
        "root_key": row.root_key,
        "item_ids": row.item_ids,
        "status": row.status,
        "progress": progress,
        "error": row.error,
        "warnings": row.warnings,
        "report_type": row.report_type,
        "created_at": datetime.fromisoformat(row.created_at),
        "updated_at": datetime.fromisoformat(row.updated_at),
        "finished_at": datetime.fromisoformat(row.finished_at) if row.finished_at else None,
    }


class JobStore:
    """Agent jobs in a SQLite file, one short transaction per operation."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._engine: Engine | None = None
        self._lock = threading.Lock()

    def _get_engine(self) -> Engine:
        with self._lock:
            if self._engine is None:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                engine = sa.create_engine(f"sqlite:///{self.path}", connect_args={"timeout": 5.0})
                try:
                    _metadata.create_all(engine)
                except Exception:
                    engine.dispose()
                    raise
                self._engine = engine
            return self._engine

    def _write(self, action: str, job_id: str | None, work: Callable[[Engine], T]) -> T | None:
        """Run *work* and swallow its failure; ``None`` means it did not happen."""
        try:
            return work(self._get_engine())
        except (SQLAlchemyError, OSError, TypeError, ValueError) as e:
            target = f" job '{job_id}'" if job_id else " jobs"
            logger.warning("Could not %s%s in '%s': %r", action, target, self.path, e)
            return None

    def create(
        self,
        job_id: str,
        *,
        agent_key: str,
        user_key: str,
        project_key: str,
        project_name: str,
        root_key: str | None,
        item_ids: list[str],
        warnings: list[str],
    ) -> None:
        """Insert a new job in state ``running``."""
        now = _iso(_now())

        def work(engine: Engine) -> None:
            with engine.begin() as conn:
                conn.execute(
                    _jobs.insert().values(
                        id=job_id,
                        agent_key=agent_key,
                        user_key=user_key,
                        project_key=project_key,
                        project_name=project_name,
                        root_key=root_key,
                        item_ids=item_ids,
                        status="running",
                        warnings=warnings,
                        created_at=now,
                        updated_at=now,
                    )
                )

        self._write("create", job_id, work)

    def progress(self, job_id: str, done: int, total: int, text: str | None) -> None:
        """Record how far the job is."""
        self._write(
            "update progress of",
            job_id,
            lambda engine: self._update(
                engine, job_id, progress_done=done, progress_total=total, progress_text=text
            ),
        )

    def add_warning(self, job_id: str, message: str) -> None:
        """Append *message* to the job's warnings."""

        def work(engine: Engine) -> None:
            with engine.begin() as conn:
                row = conn.execute(sa.select(_jobs.c.warnings).where(_jobs.c.id == job_id)).first()
                if row is None:
                    return
                current = row.warnings
                conn.execute(
                    _jobs.update()
                    .where(_jobs.c.id == job_id)
                    .values(warnings=[*current, message], updated_at=_iso(_now()))
                )

        self._write("add a warning to", job_id, work)

    def set_report(self, job_id: str, report_type: str, report: Any) -> None:
        """Store the job's report; a value that is not JSON is logged and dropped."""

        def work(engine: Engine) -> None:
            json.dumps(report)  # fail here, not half-way into the statement
            self._update(engine, job_id, report_type=report_type, report=report)

        self._write("store the report of", job_id, work)

    def finish(
        self, job_id: str, status: Literal["succeeded", "failed"], error: str | None = None
    ) -> None:
        """End a running job; a job that already ended keeps its first outcome."""
        now = _iso(_now())

        def work(engine: Engine) -> None:
            with engine.begin() as conn:
                conn.execute(
                    _jobs.update()
                    .where(_jobs.c.id == job_id, _jobs.c.status == "running")
                    .values(status=status, error=error, updated_at=now, finished_at=now)
                )

        self._write("finish", job_id, work)

    def abort_running(self, message: str) -> int:
        """Fail every job still ``running``; returns how many there were."""
        now = _iso(_now())

        def work(engine: Engine) -> int:
            with engine.begin() as conn:
                result = conn.execute(
                    _jobs.update()
                    .where(_jobs.c.status == "running")
                    .values(status="failed", error=message, updated_at=now, finished_at=now)
                )
                return result.rowcount

        return self._write("abort running", None, work) or 0

    def purge_older_than(self, days: int) -> int:
        """Delete jobs created more than *days* days ago; returns how many."""
        cutoff = _iso(_now() - timedelta(days=days))

        def work(engine: Engine) -> int:
            with engine.begin() as conn:
                return conn.execute(_jobs.delete().where(_jobs.c.created_at < cutoff)).rowcount

        return self._write("purge old", None, work) or 0

    @staticmethod
    def _update(engine: Engine, job_id: str, **values: Any) -> None:
        with engine.begin() as conn:
            conn.execute(
                _jobs.update().where(_jobs.c.id == job_id).values(**values, updated_at=_iso(_now()))
            )

    def get(self, job_id: str, user_key: str) -> JobDetail | None:
        """The job, or ``None`` if it does not exist or belongs to someone else.

        Raises ``SQLAlchemyError`` or ``OSError`` -- the caller decides how to
        show that the read failed.
        """
        with self._get_engine().connect() as conn:
            row = conn.execute(
                sa.select(_jobs).where(_jobs.c.id == job_id, _jobs.c.user_key == user_key)
            ).first()
        if row is None:
            return None
        return JobDetail(**_summary_fields(row), report=row.report)

    def list_for_user(
        self,
        user_key: str,
        *,
        agent_key: str | None = None,
        status: JobStatus | None = None,
        limit: int = 50,
    ) -> list[JobSummary]:
        """The user's jobs without reports, newest first.

        Raises like ``get``.
        """
        query = sa.select(*_SUMMARY_COLUMNS).where(_jobs.c.user_key == user_key)
        if agent_key is not None:
            query = query.where(_jobs.c.agent_key == agent_key)
        if status is not None:
            query = query.where(_jobs.c.status == status)
        query = query.order_by(_jobs.c.created_at.desc()).limit(limit)
        with self._get_engine().connect() as conn:
            rows = conn.execute(query).all()
        return [JobSummary(**_summary_fields(row)) for row in rows]

    async def run(self, fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """Call *fn* off the event loop: a SQLite commit waits on the disk."""
        return await asyncio.to_thread(fn, *args, **kwargs)


def get_job_store(request: Request) -> JobStore:
    """FastAPI dependency: the process's job store."""
    store: JobStore = request.app.state.job_store
    return store
