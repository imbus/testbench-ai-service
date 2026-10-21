"""Console authentication: TestBench login, cookies, CSRF, and role checks."""

import secrets
from dataclasses import dataclass

from fastapi import Cookie, Depends, Header, HTTPException, Request, Response, status
from testbench_cli_reporter.testbench import Connection as TBConnection

from testbench_ai_service.config import AppConfig
from testbench_ai_service.log import log_user_key, log_username, logger
from testbench_ai_service.models.testbench import GlobalHumanRole
from testbench_ai_service.utils.testbench import get_user_key
from testbench_ai_service.webui.projects import ProjectFetch, fetch_projects
from testbench_ai_service.webui.session import (
    CSRF_COOKIE,
    CSRF_HEADER,
    SESSION_COOKIE,
    Session,
    SessionStore,
)
from testbench_ai_service.webui.tb_link import TestBenchLink, open_connection


def get_session_store(request: Request) -> SessionStore:
    store: SessionStore = request.app.state.webui_sessions
    return store


def is_admin_role(roles: list[str]) -> bool:
    """True when *roles* grants global administration.

    The role list differs between TestBench 3 and 4 and can contain
    ``"Project User"`` with a space, so only the exact administrator string counts.
    """
    return GlobalHumanRole.Administrator.value in roles


@dataclass(frozen=True)
class LoginResult:
    """Everything one login yields.

    ``link`` holds the login connection, still open: its heartbeat is what
    keeps the TestBench session token alive (TestBench 4 drops an idle one
    after about five minutes), and it logs in again if TestBench ends the
    session anyway. The session store owns it from here and closes it.

    ``projects`` rides along because the login connection is already
    authenticated (design D3). It always carries a result -- a failed fetch is
    an ``error`` on it, never an exception, so an unreachable project endpoint
    cannot fail the login (D4).
    """

    roles: list[str]
    projects: ProjectFetch
    link: TestBenchLink
    user_key: str | None = None


def _read_user_key(conn: TBConnection) -> str | None:
    """The TestBench user key, or None -- never a reason to fail the login (design 4.4)."""
    try:
        key = get_user_key(conn)
    except Exception as e:  # any failure here only costs the activity view
        logger.warning("Could not read the TestBench user key for the console session: %r", e)
        return None
    return key if isinstance(key, str) and key else None


def authenticate(config: AppConfig, username: str, password: str) -> LoginResult:
    """Log in to TestBench and read everything the connection can give us.

    Raises:
        HTTPException 401: TestBench rejected the credentials.
        HTTPException 500: ``tb_server_url`` is not a usable TestBench URL.
        HTTPException 502: TestBench is unreachable, or rejected the request for
            a reason other than the credentials themselves.
    """
    conn, roles = open_connection(config, username, password)
    # fetch_projects and _read_user_key never raise, so nothing past this point
    # can leave the open connection without an owner.
    return LoginResult(
        roles=roles,
        projects=fetch_projects(conn),
        link=TestBenchLink(config, username, password, conn),
        user_key=_read_user_key(conn),
    )


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


async def bind_log_user(session: Session = Depends(current_session)) -> Session:
    """Tag every record of this request with the signed-in user (design 4.3).

    Async on purpose: async dependencies run in the request's own task, so the
    values reach the endpoint -- and, through run_in_threadpool's context copy,
    sync endpoints too. A sync dependency would set them in a threadpool copy
    and lose them. No reset: the request task ends with the response.
    """
    log_user_key.set(session.user_key)
    log_username.set(session.username)
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
