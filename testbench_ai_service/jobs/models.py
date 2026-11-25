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
    root_uid: str | None = None
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
    #: The report as JSON text, exactly as stored. A browser reads numbers as
    #: doubles, so past 2^53 its own rendering of ``report`` shows another value.
    report_json: str | None = None


#: Exceptions whose text alone says nothing: ``KeyError('x')`` reads "'x'".
_BARE_ERRORS = (LookupError, AttributeError, TypeError, AssertionError, NotImplementedError)


def describe_error(error: BaseException) -> str:
    """An exception as a job shows it to the person who started the job.

    The message, not the Python expression: ``ValueError("API key not found")``
    is stored as "API key not found". Where the message is empty or means
    nothing without the kind of error, the kind is put in front.
    """
    text = str(error).strip()
    if not text:
        return type(error).__name__
    if isinstance(error, _BARE_ERRORS):
        return f"{type(error).__name__}: {text}"
    return text


class JobViewTicket(BaseModel):
    """Where to open a job in the browser, and the one-time ticket to get in."""

    view_path: str
    view_token: str  # named *token* so the request logging masks it
    expires_in: int
