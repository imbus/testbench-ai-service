"""``GET /jobs/{job_id}``: the TestBench client plugin reads a job it triggered."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.exc import SQLAlchemyError

from testbench_ai_service.auth import AuthInfo, validate_auth_token
from testbench_ai_service.exceptions import HTTPError
from testbench_ai_service.jobs.models import JobDetail, JobViewTicket
from testbench_ai_service.jobs.store import JobStore, get_job_store
from testbench_ai_service.jobs.view import (
    TICKET_TTL,
    JobViewStore,
    get_job_view_store,
    view_path,
)
from testbench_ai_service.log import logger
from testbench_ai_service.models.language import LanguageOption

router = APIRouter(tags=["Jobs"], dependencies=[Depends(validate_auth_token)])


def _read_own_job(job_store: JobStore, job_id: str, user_key: str) -> JobDetail:
    """The user's job; 404 for an unknown or foreign one, 503 if the read fails."""
    try:
        job = job_store.get(job_id, user_key)
    except (SQLAlchemyError, OSError) as e:
        logger.warning("Could not read job '%s': %r", job_id, e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Jobs are temporarily unavailable",
        ) from e
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    return job


@router.get(
    "/jobs/{job_id}",
    response_model=JobDetail,
    summary="Get an agent job",
    responses={
        status.HTTP_404_NOT_FOUND: {"model": HTTPError},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": HTTPError},
    },
)
def get_job(
    job_id: str,
    auth_info: AuthInfo = Depends(validate_auth_token),
    job_store: JobStore = Depends(get_job_store),
) -> JobDetail:
    """The job with its report, only for the user who triggered it.

    A job of another user is answered exactly like an unknown one (404),
    for admins as well. A sync ``def``: the read hits SQLite, so it belongs
    in the threadpool.
    """
    return _read_own_job(job_store, job_id, auth_info.user_key)


@router.post(
    "/jobs/{job_id}/view-ticket",
    response_model=JobViewTicket,
    summary="Get a link that opens the job in a browser",
    responses={
        status.HTTP_404_NOT_FOUND: {"model": HTTPError},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": HTTPError},
    },
)
def create_job_view_ticket(
    job_id: str,
    request: Request,
    language: LanguageOption | None = Query(default=None),
    auth_info: AuthInfo = Depends(validate_auth_token),
    job_store: JobStore = Depends(get_job_store),
    view_store: JobViewStore = Depends(get_job_view_store),
) -> JobViewTicket:
    """A one-time ticket that opens the job's browser page without the ``Authorization`` header.

    Open ``{view_path}?view_token={view_token}`` within ``expires_in`` seconds.
    The page shows the job like ``GET /jobs/{job_id}`` and refreshes itself
    while the job runs. Only the user who triggered the job gets a ticket.
    """
    _read_own_job(job_store, job_id, auth_info.user_key)
    ticket = view_store.issue_ticket(
        job_id,
        auth_info.user_key,
        language or request.app.state.config.language,
    )
    return JobViewTicket(
        view_path=view_path(job_id),
        view_token=ticket,
        expires_in=int(TICKET_TTL.total_seconds()),
    )
