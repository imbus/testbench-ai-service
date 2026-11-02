"""Pydantic models for agent jobs as the API returns them."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

JobStatus = Literal["running", "succeeded", "failed"]


class JobProgress(BaseModel):
    """How far a running job is."""

    done: int
    total: int
    text: str | None = None


class JobSummary(BaseModel):
    """A job without its report, cheap enough to list."""

    job_id: str
    agent_key: str
    project_key: str
    project_name: str
    root_key: str | None
    item_ids: list[str]
    status: JobStatus
    progress: JobProgress | None
    error: str | None
    warnings: list[str]
    report_type: str | None
    created_at: datetime
    updated_at: datetime
    finished_at: datetime | None


class JobDetail(JobSummary):
    """A job including its report."""

    report: Any | None = None


class JobViewTicket(BaseModel):
    """Where to open a job in the browser, and the one-time ticket to get in."""

    view_path: str
    view_token: str  # named *token* so the request logging masks it
    expires_in: int
