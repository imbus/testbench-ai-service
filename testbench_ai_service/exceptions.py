from typing import NoReturn

import requests
from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse, Response
from fastapi.utils import is_body_allowed_for_status_code
from pydantic import BaseModel

from testbench_ai_service.log import logger


class HTTPError(BaseModel):
    detail: str


async def http_exception_handler(request: Request, exc: HTTPException) -> Response:
    headers = getattr(exc, "headers", None)
    if not is_body_allowed_for_status_code(exc.status_code):
        return Response(status_code=exc.status_code, headers=headers)
    error_response = HTTPError(detail=str(exc.detail))
    return JSONResponse(error_response.model_dump(), status_code=exc.status_code, headers=headers)


def handle_requests_http_error(e: requests.exceptions.HTTPError):
    """Parse a ``requests.HTTPError``, log it, and re-raise as :class:`fastapi.HTTPException`."""
    status_code = e.response.status_code if e.response is not None else None
    message = str(e)
    if e.response is not None:
        message = "Unknown Error"
        try:
            response_json = e.response.json()
            if isinstance(response_json, dict):
                message = response_json.get("message") or response_json.get("detail") or message
        except ValueError:
            response_text = e.response.text.strip()
            if response_text:
                message = response_text
    if status_code == status.HTTP_404_NOT_FOUND:
        logger.info(f"Resource not found in TestBench Server: {message}")
    elif status_code and 400 <= status_code < 500:  # noqa: PLR2004
        logger.warning(f"Client error from TestBench Server: {status_code} - {message}")
    else:
        logger.error(f"Server error from TestBench Server: {status_code} - {message}")
    raise HTTPException(
        status_code=status_code or status.HTTP_500_INTERNAL_SERVER_ERROR, detail=message
    ) from e


#: Transport-level failures of an outbound TestBench call: the server could not be
#: reached, or it accepted the connection and then never answered.  ``ReadTimeout``
#: derives from ``Timeout`` only - not from ``ConnectionError`` - so catching
#: ``ConnectionError`` alone lets a stalled read escape as an unhandled 500.
TRANSPORT_ERRORS = (requests.exceptions.ConnectionError, requests.exceptions.Timeout)


def handle_requests_transport_error(e: requests.exceptions.RequestException) -> NoReturn:
    """Log a TestBench transport failure and re-raise it as HTTP 502.

    Bounded timeouts (``connection_timeout_sec`` on the connection plus
    :func:`~testbench_ai_service.transport.harden_connection`) mean a hung TestBench
    server now raises ``requests.exceptions.Timeout`` instead of hanging forever.  From
    a caller's point of view that is the same failure as an unreachable server: the
    upstream did not deliver a response, so both map to ``502 Bad Gateway``.
    """
    if isinstance(e, requests.exceptions.Timeout):
        detail = f"TestBench server did not respond in time: {e!s}"
    else:
        detail = f"Could not connect to TestBench server: {e!s}"
    logger.error(detail)
    raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail) from e
