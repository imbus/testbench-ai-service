"""A console session's live TestBench connection, renewed when it dies.

TestBench 4 drops a session token after about five minutes without traffic.
The vendored ``Connection`` keeps its token alive with a heartbeat thread, but
only while the connection is open -- so the login connection is no longer
closed once the login is done. It stays open for the life of the console
session, and :meth:`TestBenchLink.close` is what stops the heartbeat.

The heartbeat cannot cover everything: a TestBench restart, a forced login of
the same user elsewhere, or a network outage longer than the token lifetime
still ends the session server-side. For those, the link keeps the operator's
credentials in memory and logs in again on demand. This is the same trade the
store already made on TestBench 3, where the "token" is the plaintext password
(see :mod:`~testbench_ai_service.webui.session`).
"""

import math
import threading
from collections.abc import Callable
from typing import TypeVar

import requests
from fastapi import HTTPException, status
from testbench_cli_reporter.testbench import Connection as TBConnection

from testbench_ai_service.config import AppConfig
from testbench_ai_service.exceptions import TRANSPORT_ERRORS, handle_requests_transport_error
from testbench_ai_service.log import logger
from testbench_ai_service.transport import (
    DEFAULT_CONNECT_TIMEOUT,
    DEFAULT_READ_TIMEOUT,
    harden_connection,
)

T = TypeVar("T")


def open_connection(
    config: AppConfig, username: str, password: str
) -> tuple[TBConnection, list[str]]:
    """Log in to TestBench and return the open connection and the user's roles.

    The connection is returned open, heartbeat running; the caller owns it.
    On any failure it is closed before the exception propagates.

    Raises:
        HTTPException 401: TestBench rejected the credentials.
        HTTPException 500: ``tb_server_url`` is not a usable TestBench URL.
        HTTPException 502: TestBench is unreachable, or rejected the request for
            a reason other than the credentials themselves (e.g. a 503 while the
            server is starting up, or a wrong-but-shape-valid URL path).
    """
    try:
        conn = TBConnection(
            config.tb_server_url,
            verify=config.tb_ssl_ca_bundle or config.tb_ssl_verify,
            loginname=username,
            password=password,
            connection_timeout_sec=math.ceil(DEFAULT_READ_TIMEOUT),
        )
    except ValueError as e:
        # TBConnection validates the URL shape here, and only here. A ValueError
        # raised later (e.g. read_user_roles' "User key not found in checkLogin
        # response" on the TestBench 3 path) is not a configuration problem and
        # must not be caught by this branch -- hence the narrow try above.
        logger.error("Cannot log in to TestBench: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"TestBench server URL is not usable, check the configuration: {e}",
        ) from e

    try:
        harden_connection(
            conn,
            connect_timeout=DEFAULT_CONNECT_TIMEOUT,
            read_timeout=DEFAULT_READ_TIMEOUT,
        )
        roles = conn.read_user_roles(conn.session)
        if not conn.session_token:
            # Defends against a real defect in the vendored library: on the
            # TestBench 4 path, Connection.authenticate swallows an HTTPError
            # that carries a response, so a wrong password can leave
            # session_token as None and raise nothing at all.
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
            )
        return conn, list(roles)
    except HTTPException:
        conn.close()
        raise
    except requests.exceptions.HTTPError as e:
        conn.close()
        response_status = e.response.status_code if e.response is not None else None
        if response_status in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN):
            logger.warning("Console login rejected for user %r", username)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
            ) from e
        # Any other status (a 503 while TestBench is starting up, a wrong but
        # shape-valid URL path, ...) is not a credentials problem and must not
        # be reported as one.
        logger.error("TestBench returned an error during console login: %s", e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="TestBench server returned an unexpected error",
        ) from e
    except TRANSPORT_ERRORS as e:
        conn.close()
        handle_requests_transport_error(e)
    except BaseException:
        conn.close()
        raise


def _is_unauthorized(error: BaseException) -> bool:
    return (
        isinstance(error, requests.exceptions.HTTPError)
        and error.response is not None
        and error.response.status_code == status.HTTP_401_UNAUTHORIZED
    )


class TestBenchLink:
    """One console session's TestBench connection, kept alive and renewed.

    Thread-safe: sync routes run in the threadpool, so two requests of the same
    session may reach the link at once. The lock is held across a whole
    :meth:`call` so neither request can renew the connection out from under
    the other.
    """

    __test__ = False  # not a pytest test class, despite the name

    def __init__(
        self,
        config: AppConfig,
        username: str,
        password: str,
        conn: TBConnection | None = None,
    ):
        self._config = config
        self._username = username
        self._password = password
        self._conn = conn
        self._lock = threading.RLock()

    def __repr__(self) -> str:
        return f"TestBenchLink(username={self._username!r})"

    @staticmethod
    def _is_alive(conn: TBConnection | None) -> bool:
        # The heartbeat sets session_terminated when TestBench answers 401.
        # Compared with ``is True`` so a test double's auto-attribute does not
        # read as a dead session.
        return conn is not None and conn.session_terminated is not True

    def connection(self) -> TBConnection:
        """The live connection, logging in again first if TestBench ended it.

        Raises:
            HTTPException: as :func:`open_connection`, when the renewal fails.
        """
        with self._lock:
            if not self._is_alive(self._conn):
                return self.renew()
            assert self._conn is not None
            return self._conn

    def renew(self) -> TBConnection:
        """Close the current connection and log in with the stored credentials."""
        with self._lock:
            logger.info("Renewing the TestBench session for console user %r", self._username)
            self._close_conn()
            self._conn, _ = open_connection(self._config, self._username, self._password)
            return self._conn

    def call(self, fn: Callable[[TBConnection], T]) -> T:
        """Run *fn* on the live connection, renewing once if TestBench answers 401.

        The heartbeat only notices a dead token every few seconds, so a request
        can still hit one in between; that single 401 is retried on a fresh
        login rather than reported.
        """
        with self._lock:
            conn = self.connection()
            try:
                return fn(conn)
            except requests.exceptions.HTTPError as e:
                if not _is_unauthorized(e):
                    raise
                logger.info("TestBench rejected the session token; logging in again")
                return fn(self.renew())

    def _close_conn(self) -> None:
        conn, self._conn = self._conn, None
        if conn is None:
            return
        try:
            conn.close()
        except Exception as e:  # a dead connection must not block its replacement
            logger.debug("Closing a TestBench connection failed: %r", e)

    def close(self) -> None:
        """Stop the heartbeat and drop the connection. Idempotent."""
        with self._lock:
            self._close_conn()
