"""A browser page for one job, opened from the TestBench client plugin.

A browser cannot send the plugin's ``Authorization`` header, so the plugin
trades it for a ticket first (``POST /jobs/{job_id}/view-ticket``) and opens
``/jobs/{job_id}/view?view_token=<ticket>``. The ticket is short-lived and
works once: redeeming it opens a view session bound to that job and user,
kept in an HttpOnly cookie scoped to the job's view path, and redirects to the
same path without the ticket, so it does not stay in the address bar or the
browser history. The JWT itself never leaves the plugin.

Tickets and view sessions are process-local, like the console's sessions: a
restart ends them, and the plugin hands out a new link on the next click.

The page itself is a small build of the console (``frontend/job-view.html``,
built into ``static/job-view``) that shows the job as the console's job page
does. It is served from here, not from ``/admin``, so it also works with the
console switched off.
"""

import html
import json
import secrets
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from sqlalchemy.exc import SQLAlchemyError

from testbench_ai_service.jobs.models import JobDetail
from testbench_ai_service.jobs.store import JobStore, get_job_store
from testbench_ai_service.log import logger
from testbench_ai_service.models.language import LanguageOption
from testbench_ai_service.utils.i18n import get_translation

TICKET_TTL = timedelta(minutes=2)
SESSION_TTL = timedelta(hours=8)

VIEW_COOKIE = "tbai_job_view"

JOB_VIEW_DIR = (Path(__file__).parent.parent / "static" / "job-view").resolve()

_CONFIG_MARKER = "<!--job-view-config-->"

# Windows may map these to the wrong type from the registry; a module script
# served as text/plain does not run.
_ASSET_TYPES = {
    ".js": "text/javascript",
    ".css": "text/css",
    ".woff2": "font/woff2",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class _Grant:
    """Who may see which job, until when, and in which language."""

    job_id: str
    user_key: str
    language: LanguageOption
    expires_at: datetime


class JobViewStore:
    """One-time tickets and the view sessions they open, in memory."""

    def __init__(
        self,
        ticket_ttl: timedelta = TICKET_TTL,
        session_ttl: timedelta = SESSION_TTL,
        now: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._tickets: dict[str, _Grant] = {}
        self._sessions: dict[str, _Grant] = {}
        self._ticket_ttl = ticket_ttl
        self._session_ttl = session_ttl
        self._now = now
        # Routes run sync handlers in the threadpool, so two requests can meet here.
        self._lock = threading.Lock()

    def issue_ticket(
        self,
        job_id: str,
        user_key: str,
        language: LanguageOption,
    ) -> str:
        """A ticket that opens one view session for *job_id*."""
        ticket = secrets.token_urlsafe(32)
        with self._lock:
            moment = self._now()
            self._drop_expired(moment)
            self._tickets[ticket] = _Grant(job_id, user_key, language, moment + self._ticket_ttl)
        return ticket

    def redeem_ticket(self, job_id: str, ticket: str) -> str | None:
        """Use up *ticket* and return a new session id, or ``None`` if it is not valid.

        A ticket is consumed even when it is presented for another job, so a
        guessed or leaked ticket cannot be retried.
        """
        with self._lock:
            moment = self._now()
            grant = self._tickets.pop(ticket, None)
            if grant is None or grant.expires_at < moment or grant.job_id != job_id:
                return None
            sid = secrets.token_urlsafe(32)
            self._sessions[sid] = _Grant(
                job_id, grant.user_key, grant.language, moment + self._session_ttl
            )
            return sid

    def session(self, job_id: str, sid: str | None) -> _Grant | None:
        """The live session *sid* for *job_id*, or ``None``."""
        if not sid:
            return None
        with self._lock:
            grant = self._sessions.get(sid)
            if grant is None:
                return None
            if grant.expires_at < self._now():
                self._sessions.pop(sid, None)
                return None
        return grant if grant.job_id == job_id else None

    def _drop_expired(self, moment: datetime) -> None:
        for entries in (self._tickets, self._sessions):
            for key, grant in list(entries.items()):
                if grant.expires_at < moment:
                    entries.pop(key, None)


def get_job_view_store(request: Request) -> JobViewStore:
    """FastAPI dependency: the process's job view tickets and sessions."""
    store: JobViewStore = request.app.state.job_view_store
    return store


def view_path(job_id: str) -> str:
    """The path of the job's browser page, which also scopes its cookie."""
    return f"/jobs/{quote(job_id, safe='')}/view"


def _cookie_secure(request: Request) -> bool:
    """True only when TLS is configured, matching the scheme cookies travel over."""
    config = request.app.state.config
    return bool(config.ssl_cert and config.ssl_key)


def _page_headers(nonce: str | None = None) -> dict[str, str]:
    styles = f"'self' 'nonce-{nonce}'" if nonce else "'self'"
    return {
        # PrimeReact injects <style> elements (the nonce) and sets style attributes.
        "Content-Security-Policy": (
            f"default-src 'none'; script-src 'self'; style-src {styles}; "
            "style-src-attr 'unsafe-inline'; font-src 'self'; img-src 'self' data:; "
            "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
        ),
        "Referrer-Policy": "no-referrer",
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
    }


def _expired_page(language: LanguageOption, status_code: int) -> HTMLResponse:
    return _render_page(language, {"expired": True}, status_code)


def _job_page(job_id: str, language: LanguageOption, console: bool) -> HTMLResponse:
    page_config: dict[str, object] = {"dataUrl": view_path(job_id) + "/data"}
    if console:
        # Where the page's sign-in to the console leads.
        page_config["consoleUrl"] = f"/admin/jobs/{quote(job_id, safe='')}"
    return _render_page(language, page_config)


def _render_page(
    language: LanguageOption,
    page_config: dict[str, object],
    status_code: int = status.HTTP_200_OK,
) -> HTMLResponse:
    template_file = JOB_VIEW_DIR / "job-view.html"
    if not template_file.is_file():
        logger.warning("Job page assets not found at %s; build the frontend", JOB_VIEW_DIR)
        message = html.escape(get_translation("jobs.view.not_built", language))
        body = (
            f'<!doctype html><html lang="{language.value}"><meta charset="utf-8"><p>{message}</p>'
        )
        return HTMLResponse(body, status_code=status_code, headers=_page_headers())
    nonce = secrets.token_urlsafe(16)
    config = {**page_config, "language": language.value, "nonce": nonce}
    # Inside <script type="application/json"> only "</" could end the element early.
    config_json = json.dumps(config, ensure_ascii=False).replace("</", "<\\/")
    page = (
        template_file.read_text(encoding="utf-8")
        .replace('<html lang="de">', f'<html lang="{language.value}">', 1)
        .replace(
            _CONFIG_MARKER,
            f'<script type="application/json" id="job-view-config">{config_json}</script>',
            1,
        )
    )
    return HTMLResponse(page, status_code=status_code, headers=_page_headers(nonce))


view_router = APIRouter(tags=["Jobs"])


@view_router.get("/jobs/{job_id}/view", include_in_schema=False, response_model=None)
def view_job(
    job_id: str,
    request: Request,
    view_token: str | None = Query(default=None),
    session_id: str | None = Cookie(default=None, alias=VIEW_COOKIE),
    store: JobViewStore = Depends(get_job_view_store),
) -> Response:
    """Redeem a ticket into a view session, or show the page of a session already open."""
    language = request.app.state.config.language
    if view_token is not None:
        sid = store.redeem_ticket(job_id, view_token)
        if sid is None:
            logger.info("Rejected an invalid or expired view ticket for job '%s'", job_id)
            return _expired_page(language, status.HTTP_401_UNAUTHORIZED)
        response = RedirectResponse(view_path(job_id), status_code=status.HTTP_303_SEE_OTHER)
        response.set_cookie(
            VIEW_COOKIE,
            sid,
            max_age=int(SESSION_TTL.total_seconds()),
            httponly=True,
            # Lax, not strict: the page is opened from the TestBench client, which
            # the browser treats as an outside navigation.
            samesite="lax",
            secure=_cookie_secure(request),
            path=view_path(job_id),
        )
        for name, value in _page_headers().items():
            response.headers[name] = value
        return response

    grant = store.session(job_id, session_id)
    if grant is None:
        return _expired_page(language, status.HTTP_401_UNAUTHORIZED)
    return _job_page(job_id, grant.language, request.app.state.config.admin_ui.enabled)


@view_router.get("/jobs/view-assets/assets/{name}", include_in_schema=False, response_model=None)
def view_asset(name: str) -> Response:
    """A script, stylesheet or font of the job page; the build gives them hashed names."""
    file = JOB_VIEW_DIR / "assets" / name
    if Path(name).name != name or not file.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    return FileResponse(
        file,
        media_type=_ASSET_TYPES.get(file.suffix.lower()),
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


@view_router.get("/jobs/{job_id}/view/data", include_in_schema=False, response_model=JobDetail)
def view_job_data(
    job_id: str,
    response: Response,
    session_id: str | None = Cookie(default=None, alias=VIEW_COOKIE),
    store: JobViewStore = Depends(get_job_view_store),
    job_store: JobStore = Depends(get_job_store),
) -> JobDetail:
    """The job as ``GET /jobs/{job_id}`` returns it, for the page's view session."""
    grant = store.session(job_id, session_id)
    if grant is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="View expired")
    try:
        job = job_store.get(job_id, grant.user_key)
    except (SQLAlchemyError, OSError) as e:
        logger.warning("Could not read job '%s' for its view: %r", job_id, e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Jobs are temporarily unavailable",
        ) from e
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    response.headers["Cache-Control"] = "no-store"
    return job
