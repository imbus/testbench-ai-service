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


#: Builtin ``OSError`` subclasses raised when the peer tears down a connection that was
#: already established: ECONNRESET (WSAECONNRESET / Windows error 10054), ECONNABORTED
#: and EPIPE.  Reaching the server and losing the socket mid-request is a different
#: failure from never reaching it, but ``requests`` reports both as ``ConnectionError``.
PEER_CLOSED_ERRORS = (ConnectionResetError, ConnectionAbortedError, BrokenPipeError)


def peer_closed_connection(e: BaseException) -> bool:
    """Return True if *e* was caused by the peer dropping an established connection.

    The distinguishing cause is buried: ``requests`` wraps ``urllib3``, which wraps the
    original ``OSError``, and neither uses a single attribute to expose it.  So the whole
    cause chain is walked - ``__cause__``/``__context__``, the exceptions passed along as
    ``args`` (``ProtocolError('Connection aborted.', ConnectionResetError(...))``), and
    ``MaxRetryError.reason`` - looking for one of :data:`PEER_CLOSED_ERRORS`.
    """
    seen: set[int] = set()
    stack: list[BaseException] = [e]
    while stack:
        current = stack.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, PEER_CLOSED_ERRORS):
            return True
        stack.extend(arg for arg in getattr(current, "args", ()) if isinstance(arg, BaseException))
        stack.extend(
            nested for nested in (current.__cause__, current.__context__) if nested is not None
        )
        reason = getattr(current, "reason", None)  # urllib3.exceptions.MaxRetryError
        if isinstance(reason, BaseException):
            stack.append(reason)
    return False


#: Attribute under which :class:`~testbench_ai_service.middlewares.TestBenchRequestLogger`
#: parks how long a failed outbound call ran, for :func:`handle_requests_transport_error`
#: to read back.  An attribute on the exception is the only channel available: the error
#: travels up through ``requests``, which offers nowhere else to put it.
ELAPSED_ATTRIBUTE = "testbench_elapsed_seconds"


def record_elapsed(e: BaseException, seconds: float) -> None:
    """Note on *e* how long the failed request ran before it gave up.

    Best effort by design - an exception type that refuses the attribute costs the
    caller a detail in the message, which is never worth masking the original error.
    """
    try:
        setattr(e, ELAPSED_ATTRIBUTE, seconds)
    except (AttributeError, TypeError):  # e.g. an exception class using __slots__
        logger.debug("Could not record elapsed time on %s", type(e).__name__)


def _elapsed_phrase(e: BaseException) -> str:
    """Render the recorded duration, or nothing if the call was not timed.

    The duration is what identifies this failure: a server-side idle timeout lands on
    the same constant every time (75 s for a stock TestBench), whereas a genuine network
    fault does not.  Without it in the message, a reader has only an opaque socket error
    to go on and no reason to suspect a timeout at all.
    """
    elapsed = getattr(e, ELAPSED_ATTRIBUTE, None)
    if not isinstance(elapsed, (int, float)) or isinstance(elapsed, bool):
        return ""
    return f" after {elapsed:.1f}s"


def handle_requests_transport_error(e: requests.exceptions.RequestException) -> NoReturn:
    """Log a TestBench transport failure and re-raise it as HTTP 502.

    Bounded timeouts (``connection_timeout_sec`` on the connection plus
    :func:`~testbench_ai_service.transport.harden_connection`) mean a hung TestBench
    server now raises ``requests.exceptions.Timeout`` instead of hanging forever.  From
    a caller's point of view that is the same failure as an unreachable server: the
    upstream did not deliver a response, so all of these map to ``502 Bad Gateway``.

    The three transport failures are reported separately because they point at different
    culprits.  "Could not connect" sends whoever reads it to the URL, the port and the
    TLS settings; when the request was in fact delivered and the server then dropped the
    socket, that is the wrong place to look - the culprit is the upstream, and only it
    can say why it gave up.

    Reaching this function means every retry that applied has already been spent - the
    adapter's for idempotent methods, and
    :func:`~testbench_ai_service.transport.retry_read_only_post` for the structure
    queries - so the message is genuinely all the caller has left to go on.  Hence the
    elapsed time from :func:`_elapsed_phrase`: a failure that lands on the same duration
    every time is a configured timeout, not a network fault, and the number is what makes
    that visible.
    """
    elapsed = _elapsed_phrase(e)
    if isinstance(e, requests.exceptions.Timeout):
        detail = f"TestBench server did not respond in time{elapsed}: {e!s}"
    elif peer_closed_connection(e):
        detail = f"TestBench server closed the connection before responding{elapsed}: {e!s}"
    else:
        detail = f"Could not connect to TestBench server{elapsed}: {e!s}"
    request = getattr(e, "request", None)
    if request is None:
        logger.error(detail)
    else:
        logger.error("%s (%s %s)", detail, request.method, request.url)
    raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail) from e
