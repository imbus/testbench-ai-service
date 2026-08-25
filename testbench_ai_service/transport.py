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
connection failures on idempotent methods.
"""

from typing import TYPE_CHECKING

from requests import PreparedRequest, Response
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from testbench_ai_service.log import logger

if TYPE_CHECKING:
    from testbench_cli_reporter.testbench import Connection as TBConnection

DEFAULT_CONNECT_TIMEOUT = 10.0
DEFAULT_READ_TIMEOUT = 120.0
DEFAULT_MAX_RETRIES = 3

#: Sleep between retries is ``backoff_factor * (2 ** (attempt - 1))`` seconds.
BACKOFF_FACTOR = 0.5


class ResilientHTTPAdapter(HTTPAdapter):
    """Adapter that applies a default timeout without discarding explicit ones.

    Unlike ``testbench_cli_reporter.testbench.TimeoutHTTPAdapter`` the default is used
    only when the caller did not ask for a timeout of its own.
    """

    def __init__(self, *args, timeout: tuple[float, float] | None = None, **kwargs) -> None:
        self.timeout = timeout
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
