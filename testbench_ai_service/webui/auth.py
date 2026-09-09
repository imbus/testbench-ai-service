"""Console authentication: TestBench login, cookies, CSRF, and role checks."""

import math
import secrets

import requests
from fastapi import Cookie, Depends, Header, HTTPException, Request, Response, status
from testbench_cli_reporter.testbench import Connection as TBConnection

from testbench_ai_service.config import AppConfig
from testbench_ai_service.exceptions import TRANSPORT_ERRORS, handle_requests_transport_error
from testbench_ai_service.log import logger
from testbench_ai_service.models.testbench import GlobalHumanRole
from testbench_ai_service.transport import (
    DEFAULT_CONNECT_TIMEOUT,
    DEFAULT_READ_TIMEOUT,
    harden_connection,
)
from testbench_ai_service.webui.session import (
    CSRF_COOKIE,
    CSRF_HEADER,
    SESSION_COOKIE,
    Session,
    SessionStore,
)


def get_session_store(request: Request) -> SessionStore:
    store: SessionStore = request.app.state.webui_sessions
    return store


def is_admin_role(roles: list[str]) -> bool:
    """True when *roles* grants global administration.

    The role list differs between TestBench 3 and 4 and can contain
    ``"Project User"`` with a space, so only the exact administrator string counts.
    """
    return GlobalHumanRole.Administrator.value in roles


def authenticate(config: AppConfig, username: str, password: str) -> tuple[str, list[str]]:
    """Log in to TestBench and return ``(session_token, roles)``.

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
        token = conn.session_token
        if not token:
            # Defends against a real defect in the vendored library: on the
            # TestBench 4 path, Connection.authenticate swallows an HTTPError
            # that carries a response, so a wrong password can leave
            # session_token as None and raise nothing at all.
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
            )
        return token, list(roles)
    except requests.exceptions.HTTPError as e:
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
        handle_requests_transport_error(e)
    finally:
        conn.close()


def _cookie_secure(config: AppConfig) -> bool:
    """True only when TLS is configured, matching the scheme cookies travel over."""
    return bool(config.ssl_cert and config.ssl_key)


def set_session_cookies(response: Response, session: Session, config: AppConfig) -> None:
    """Attach the opaque session cookie and the readable CSRF cookie."""
    secure = _cookie_secure(config)
    response.set_cookie(
        SESSION_COOKIE,
        session.sid,
        httponly=True,
        samesite="strict",
        secure=secure,
        path="/admin",
    )
    response.set_cookie(
        CSRF_COOKIE,
        session.csrf_token,
        httponly=False,  # the SPA must read this to echo it back
        samesite="strict",
        secure=secure,
        path="/admin",
    )


def clear_session_cookies(response: Response, config: AppConfig) -> None:
    """Delete both cookies with the same attributes they were set with.

    ``Response.delete_cookie`` defaults to ``samesite="lax"`` and
    ``secure=False``; leaving those defaults would emit a deletion cookie that
    does not match the one being deleted.
    """
    secure = _cookie_secure(config)
    response.delete_cookie(SESSION_COOKIE, path="/admin", samesite="strict", secure=secure)
    response.delete_cookie(CSRF_COOKIE, path="/admin", samesite="strict", secure=secure)


def current_session(
    store: SessionStore = Depends(get_session_store),
    sid: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> Session:
    """The live session for this request, or 401."""
    session = store.get(sid)
    if session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not signed in")
    return session


def require_admin(session: Session = Depends(current_session)) -> Session:
    """Guard every mutating route: writes require the TestBench admin role."""
    if not session.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action requires the TestBench Administrator role",
        )
    return session


def require_csrf(
    session: Session = Depends(current_session),
    token: str | None = Header(default=None, alias=CSRF_HEADER),
) -> None:
    """Double-submit check for any state-changing request.

    Compares UTF-8-encoded bytes rather than the raw ``str``:
    ``secrets.compare_digest`` raises ``TypeError`` for ``str`` arguments that
    contain non-ASCII characters, and Starlette latin-1-decodes header bytes,
    so any client can reach that by sending a non-ASCII header value. Encoding
    first keeps a bad token a clean 403 instead of an unhandled 500.
    """
    valid = token is not None and secrets.compare_digest(
        token.encode("utf-8"), session.csrf_token.encode("utf-8")
    )
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Missing or invalid CSRF token"
        )
