"""``GET /jobs/{job_id}``: the TestBench client plugin reads a job it triggered."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError

from testbench_ai_service.auth import AuthInfo, validate_auth_token
from testbench_ai_service.exceptions import HTTPError
from testbench_ai_service.jobs.models import JobDetail
from testbench_ai_service.jobs.store import JobStore, get_job_store
from testbench_ai_service.log import logger

router = APIRouter(tags=["Jobs"], dependencies=[Depends(validate_auth_token)])


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
    try:
        job = job_store.get(job_id, auth_info.user_key)
    except (SQLAlchemyError, OSError) as e:
        logger.warning("Could not read job '%s': %r", job_id, e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Jobs are temporarily unavailable",
        ) from e
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    return job
