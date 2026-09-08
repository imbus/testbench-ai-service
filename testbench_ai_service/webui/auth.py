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
        HTTPException 502: TestBench is unreachable.
    """
    conn: TBConnection | None = None
    try:
        conn = TBConnection(
            config.tb_server_url,
            verify=config.tb_ssl_ca_bundle or config.tb_ssl_verify,
            loginname=username,
            password=password,
            connection_timeout_sec=math.ceil(DEFAULT_READ_TIMEOUT),
        )
        harden_connection(
            conn,
            connect_timeout=DEFAULT_CONNECT_TIMEOUT,
            read_timeout=DEFAULT_READ_TIMEOUT,
        )
        roles = conn.read_user_roles(conn.session)
        token = conn.session_token
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
            )
        return token, list(roles)
    except ValueError as e:
        # TBConnection validates the URL shape in __init__.
        logger.error("Cannot log in to TestBench: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"TestBench server URL is not usable, check the configuration: {e}",
        ) from e
    except requests.exceptions.HTTPError as e:
        logger.warning("Console login rejected for user %r", username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        ) from e
    except TRANSPORT_ERRORS as e:
        handle_requests_transport_error(e)
    finally:
        if conn is not None:
            conn.close()


def set_session_cookies(response: Response, session: Session, config: AppConfig) -> None:
    """Attach the opaque session cookie and the readable CSRF cookie."""
    secure = bool(config.ssl_cert and config.ssl_key)
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


def clear_session_cookies(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/admin")
    response.delete_cookie(CSRF_COOKIE, path="/admin")


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
    """Double-submit check for any state-changing request."""
    if not token or not secrets.compare_digest(token, session.csrf_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Missing or invalid CSRF token"
        )
