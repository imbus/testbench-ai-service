"""HTTP transport hardening for outbound TestBench requests.

``testbench_cli_reporter`` mounts a ``TimeoutHTTPAdapter`` on its session that has two
properties which make a single network blip fatal for a whole agent run:

* Its timeout defaults to ``None`` unless ``connection_timeout_sec`` is passed to
  ``Connection.__init__``, and its ``send`` overwrites *any* per-request timeout with
  that value. A stalled request therefore waits forever, and callers that pass their
  own timeout (the connection's own heartbeat uses ``(5, 10)``) silently lose it.
* It leaves ``max_retries`` at requests' default of zero, so a dropped keep-alive
  connection surfaces immediately as ``requests.exceptions.ConnectionError``.

:func:`harden_connection` replaces that adapter with one that applies a bounded
default timeout, honours explicit per-request timeouts, and retries transient
connection failures on idempotent methods.  :func:`retry_read_only_post` covers the
one case that policy deliberately cannot: a ``POST`` that is really a read.
"""

import time
from collections.abc import Callable
from functools import wraps
from typing import TYPE_CHECKING, ParamSpec, TypeVar

import requests
from requests import PreparedRequest, Response
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from testbench_ai_service.exceptions import peer_closed_connection
from testbench_ai_service.log import logger

if TYPE_CHECKING:
    from testbench_cli_reporter.testbench import Connection as TBConnection

#: The TestBench web server is a Play application, and ``play.server.https.idleTimeout``
#: in ``webserver/conf/application.conf`` inherits ``play.server.http.idleTimeout``,
#: whose ``play-server`` default is 75 seconds.  A request that produces no bytes for
#: that long has its socket torn down with no HTTP response at all.
PLAY_DEFAULT_IDLE_TIMEOUT = 75.0

DEFAULT_CONNECT_TIMEOUT = 10.0

#: Deliberately below :data:`PLAY_DEFAULT_IDLE_TIMEOUT`.  Waiting longer than the server
#: is willing to keep the socket open cannot rescue a slow request - the server gives up
#: first regardless - it only trades our own ``ReadTimeout``, which names the timeout
#: that fired, for the peer's connection reset, which names nothing.
DEFAULT_READ_TIMEOUT = 70.0

DEFAULT_MAX_RETRIES = 3

#: Attempts - not retries - made by :func:`retry_read_only_post` before giving up.
DEFAULT_READ_POST_ATTEMPTS = 3

#: Sleep between retries is ``backoff_factor * (2 ** (attempt - 1))`` seconds.
BACKOFF_FACTOR = 0.5

P = ParamSpec("P")
T = TypeVar("T")


class ResilientHTTPAdapter(HTTPAdapter):
    """Adapter that applies a default timeout without discarding explicit ones.

    Unlike ``testbench_cli_reporter.testbench.TimeoutHTTPAdapter`` the default is used
    only when the caller did not ask for a timeout of its own.
    """

    def __init__(self, *args, timeout: tuple[float, float] | None = None, **kwargs) -> None:
        self.timeout = timeout or (DEFAULT_CONNECT_TIMEOUT, DEFAULT_READ_TIMEOUT)
        super().__init__(*args, **kwargs)

    def send(
        self,
        request: PreparedRequest,
        stream: bool = False,
        timeout: float | tuple[float, float] | tuple[float, None] | None = None,
        verify: bool | str = True,
        cert=None,
        proxies=None,
    ) -> Response:
        return super().send(
            request,
            stream=stream,
            timeout=self.timeout if timeout is None else timeout,
            verify=verify,
            cert=cert,
            proxies=proxies,
        )


def build_retry(max_retries: int) -> Retry:
    """Retry policy for transient TestBench connection failures.

    ``allowed_methods`` is left at urllib3's idempotent default, so a request that was
    already delivered before the connection died is never replayed. That matters for
    ``PATCH`` on specifications: the server may have applied the change already, and a
    replay would append the review comment twice.
    """
    return Retry(
        total=max_retries,
        connect=max_retries,
        read=max_retries,
        status=0,
        backoff_factor=BACKOFF_FACTOR,
    )


def _response_never_arrived(e: BaseException) -> bool:
    """Return True if *e* means the server produced no response whatsoever.

    Only these are safe to replay on a non-idempotent verb: nothing was read back, so
    nothing can be duplicated by asking again.  A ``NewConnectionError`` is excluded on
    purpose even though it is equally harmless - ``Retry.increment`` does not gate
    *connect* failures on the method, so the adapter has already retried those and doing
    it again here would multiply the attempts.
    """
    return isinstance(e, requests.exceptions.Timeout) or peer_closed_connection(e)


def retry_read_only_post(
    attempts: int = DEFAULT_READ_POST_ATTEMPTS,
    backoff_factor: float = BACKOFF_FACTOR,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Retry a ``POST`` that is semantically a read, when it produced no response.

    :func:`build_retry` leaves ``allowed_methods`` at urllib3's idempotent default so a
    specification ``PATCH`` is never replayed - replaying one would append the same
    review comment twice.  The structure endpoints pay for that safety without needing
    it: they take a filter and return a tree, changing nothing, but they are spelled
    ``POST`` and so fall outside the policy.  The result is that the *only* call that is
    both slow enough to hit the server's idle timeout and safe to repeat is the one call
    that never gets repeated, and the failure reaches the caller on its first occurrence.

    Applying this per call site rather than widening ``allowed_methods`` keeps the
    distinction where it belongs.  A URL-prefix mount cannot express it either: the
    project and TOV keys are variable, so any prefix broad enough to match a structure
    request would also match the ``PATCH`` that must never be replayed.

    The wait is blocking, matching the blocking request it guards; with the defaults it
    adds at most 1.5 s.
    """

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            for attempt in range(1, attempts):
                try:
                    return func(*args, **kwargs)
                except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                    if not _response_never_arrived(e):
                        raise
                    delay = backoff_factor * (2 ** (attempt - 1))
                    logger.warning(
                        "%s got no response from TestBench (attempt %s/%s): %s - retrying in %.1fs",
                        func.__name__,
                        attempt,
                        attempts,
                        e,
                        delay,
                    )
                    time.sleep(delay)
            # The final attempt is deliberately outside the loop: whatever it raises is
            # what the caller should see, so there is no exhausted-retries branch here.
            return func(*args, **kwargs)

        return wrapper

    return decorator


def harden_connection(
    conn: "TBConnection",
    connect_timeout: float = DEFAULT_CONNECT_TIMEOUT,
    read_timeout: float = DEFAULT_READ_TIMEOUT,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> None:
    """Re-mount *conn*'s session adapters with bounded timeouts and retries.

    Accessing ``conn.session`` completes the connection's lazy setup (server version
    read, authentication, heartbeat start), so the handful of requests that setup makes
    still run on the library's own adapter. Everything afterwards - including the
    heartbeat thread, which shares the session - goes through the adapter mounted here.
    """
    adapter = ResilientHTTPAdapter(
        timeout=(connect_timeout, read_timeout),
        max_retries=build_retry(max_retries),
    )
    session = conn.session
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    logger.debug(
        "Hardened TestBench session: connect_timeout=%ss read_timeout=%ss max_retries=%s",
        connect_timeout,
        read_timeout,
        max_retries,
    )
