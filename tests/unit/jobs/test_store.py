import asyncio
import sys
from datetime import datetime, timedelta, timezone

import pytest
import sqlalchemy as sa

from testbench_ai_service.jobs import store as store_module
from testbench_ai_service.jobs.models import JobProgress, JobSummary
from testbench_ai_service.jobs.store import JobStore
from testbench_ai_service.usage import UsageStore


@pytest.fixture
def store(tmp_path) -> JobStore:
    return JobStore(tmp_path / "usage.sqlite")


def _create(
    store: JobStore, job_id: str = "j1", user_key: str = "u1", agent_key: str = "a"
) -> None:
    store.create(
        job_id,
        agent_key=agent_key,
        user_key=user_key,
        project_key="p",
        project_name="P",
        root_key=None,
        item_ids=["i1"],
        warnings=["w"],
    )


def test_create_then_get_returns_running_job(store):
    _create(store, "j1", "u1")
    job = store.get("j1", "u1")
    assert job.status == "running"
    assert job.progress is None
    assert job.report is None
    assert job.item_ids == ["i1"]
    assert job.warnings == ["w"]


def test_root_uid_is_kept_and_defaults_to_none(store):
    _create(store, "j1", "u1")
    store.create(
        "j2",
        agent_key="a",
        user_key="u1",
        project_key="p",
        project_name="P",
        root_key="REQ-1",
        root_uid="iTB-RQ-7",
        item_ids=[],
        warnings=[],
    )
    assert store.get("j1", "u1").root_uid is None
    assert store.get("j2", "u1").root_uid == "iTB-RQ-7"
    assert {job.job_id: job.root_uid for job in store.list_for_user("u1")} == {
        "j1": None,
        "j2": "iTB-RQ-7",
    }


def test_file_from_before_root_uid_gets_the_column(tmp_path):
    path = tmp_path / "usage.sqlite"
    engine = sa.create_engine(f"sqlite:///{path}")
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "CREATE TABLE agent_jobs (id VARCHAR PRIMARY KEY, agent_key VARCHAR NOT NULL,"
                " user_key VARCHAR NOT NULL, project_key VARCHAR NOT NULL,"
                " project_name VARCHAR NOT NULL, root_key VARCHAR, item_ids JSON NOT NULL,"
                " status VARCHAR NOT NULL, error VARCHAR, progress_done INTEGER,"
                " progress_total INTEGER, progress_text VARCHAR, warnings JSON NOT NULL,"
                " report_type VARCHAR, report JSON, created_at VARCHAR NOT NULL,"
                " updated_at VARCHAR NOT NULL, finished_at VARCHAR)"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO agent_jobs (id, agent_key, user_key, project_key, project_name,"
                " root_key, item_ids, status, warnings, created_at, updated_at) VALUES"
                " ('old', 'a', 'u1', 'p', 'P', 'REQ-1', '[]', 'succeeded', '[]',"
                " '2026-11-01T00:00:00.000000+00:00', '2026-11-01T00:00:00.000000+00:00')"
            )
        )
    engine.dispose()

    store = JobStore(path)
    old = store.get("old", "u1")
    assert (old.root_key, old.root_uid) == ("REQ-1", None)
    _create(store, "new", "u1")
    assert store.get("new", "u1") is not None


def test_get_other_users_job_returns_none(store):
    _create(store, "j1", "u1")
    assert store.get("j1", "u2") is None


def test_progress_report_warning_finish_roundtrip(store):
    _create(store, "j1", "u1")
    store.progress("j1", 3, 7, "Set Login")
    store.add_warning("j1", "w2")
    store.set_report("j1", "coverage_checker", {"a": 1})
    store.finish("j1", "succeeded")
    job = store.get("j1", "u1")
    assert job.progress == JobProgress(done=3, total=7, text="Set Login")
    assert job.warnings == ["w", "w2"]
    assert (job.report_type, job.report) == ("coverage_checker", {"a": 1})
    assert job.status == "succeeded"
    assert job.finished_at is not None


def test_finish_failed_keeps_first_error(store):
    _create(store, "j1", "u1")
    store.finish("j1", "failed", "agent said so")
    store.finish("j1", "failed", "RuntimeError('x')")
    assert store.get("j1", "u1").error == "agent said so"


def test_finish_succeeded_does_not_overwrite_failed(store):
    _create(store, "j1", "u1")
    store.finish("j1", "failed", "agent said so")
    store.finish("j1", "succeeded")
    assert store.get("j1", "u1").status == "failed"


def test_list_for_user_newest_first_filtered_without_report(store, monkeypatch):
    clock = iter(
        datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=m) for m in range(100)
    )
    monkeypatch.setattr(store_module, "_now", lambda: next(clock))
    _create(store, "j1", "u1", agent_key="a")
    _create(store, "j2", "u1", agent_key="b")
    _create(store, "j3", "u2", agent_key="a")
    store.finish("j1", "succeeded")
    jobs = store.list_for_user("u1")
    assert [j.job_id for j in jobs] == ["j2", "j1"]
    assert all(isinstance(j, JobSummary) and not hasattr(j, "report") for j in jobs)
    assert [j.job_id for j in store.list_for_user("u1", agent_key="a")] == ["j1"]
    assert [j.job_id for j in store.list_for_user("u1", status="running")] == ["j2"]
    assert [j.job_id for j in store.list_for_user("u1", limit=1)] == ["j2"]


def test_abort_running_marks_only_running_jobs(store):
    _create(store, "j1", "u1")
    _create(store, "j2", "u1")
    store.finish("j2", "succeeded")
    assert store.abort_running("restart") == 1
    j1 = store.get("j1", "u1")
    assert (j1.status, j1.error, j1.finished_at is not None) == ("failed", "restart", True)
    assert store.get("j2", "u1").status == "succeeded"


def test_purge_older_than_deletes_old_jobs(store, monkeypatch):
    real_now = datetime.now(timezone.utc)
    monkeypatch.setattr(store_module, "_now", lambda: real_now - timedelta(days=91))
    _create(store, "old", "u1")
    monkeypatch.setattr(store_module, "_now", lambda: real_now)
    _create(store, "new", "u1")
    assert store.purge_older_than(90) == 1
    assert store.get("old", "u1") is None
    assert store.get("new", "u1") is not None


def test_write_on_unwritable_path_is_swallowed(tmp_path, caplog):
    blocked = tmp_path / "file"
    blocked.write_text("x")
    store = JobStore(blocked / "usage.sqlite")
    store.create(
        "j1",
        agent_key="a",
        user_key="u",
        project_key="p",
        project_name="P",
        root_key=None,
        item_ids=[],
        warnings=[],
    )
    assert "Could not" in caplog.text


def test_set_report_with_unserializable_value_is_swallowed(store, caplog):
    _create(store, "j1", "u1")
    store.set_report("j1", "x", {"bad": object()})
    assert store.get("j1", "u1").report is None
    assert "Could not" in caplog.text


def test_shares_file_with_usage_store(tmp_path):
    path = tmp_path / "usage.sqlite"
    UsageStore(path).record("p", "m", None)
    _create(JobStore(path))
    assert len(UsageStore(path).totals()) == 1
    assert JobStore(path).get("j1", "u1") is not None


async def test_run_executes_in_thread(store):
    await store.run(_create, store)  # type: ignore[arg-type]
    assert store.get("j1", "u1") is not None


async def test_concurrent_warnings_are_all_kept(store):
    _create(store, "j1", "u1")
    await asyncio.gather(*(store.run(store.add_warning, "j1", f"w{i}") for i in range(30)))
    warnings = store.get("j1", "u1").warnings
    assert sorted(warnings) == sorted(["w", *(f"w{i}" for i in range(30))])


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), {"a": [float("-inf")]}])
def test_set_report_with_nan_or_infinity_is_dropped(store, bad):
    _create(store, "j1", "u1")
    store.set_report("j1", "t", bad)
    job = store.get("j1", "u1")
    assert job.report is None
    assert job.report_type is None


@pytest.mark.parametrize(
    "name",
    [
        pytest.param(
            "a?b", marks=pytest.mark.skipif(sys.platform == "win32", reason="? is not a file name")
        ),
        "c#d",
        "e%20f",
    ],
)
def test_database_path_with_url_special_characters(tmp_path, name):
    store = JobStore(tmp_path / name / "usage.sqlite")
    _create(store, "j1", "u1")
    assert store.get("j1", "u1") is not None
    assert (tmp_path / name / "usage.sqlite").exists()
