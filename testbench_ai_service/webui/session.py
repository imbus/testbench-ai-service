"""Server-side session store for the console.

The browser only ever receives an opaque session id.  The TestBench
connection stays here, so a stolen cookie cannot be replayed against TestBench.
Each session owns a :class:`~testbench_ai_service.webui.tb_link.TestBenchLink`
that keeps the TestBench session alive and logs in again when TestBench ends
it -- which means the operator's credentials are held in this store's memory
for the life of the session. A disclosure of that memory yields credentials,
not merely a replayable token (on TestBench 3 that was already true, since
the "session token" there is the plaintext password).

The store is process-local: restarting the service logs everyone out.
Every way a session ends -- revoke, expiry, shutdown -- closes its link, so no
heartbeat thread outlives the session it belongs to.
"""

import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from testbench_ai_service.webui.models import ProjectRef
from testbench_ai_service.webui.tb_link import TestBenchLink

IDLE_TIMEOUT = timedelta(minutes=60)
ABSOLUTE_TIMEOUT = timedelta(hours=8)

SESSION_COOKIE = "tbai_admin_session"
CSRF_COOKIE = "tbai_admin_csrf"
CSRF_HEADER = "X-CSRF-Token"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Session:
    """One logged-in console user."""

    sid: str
    csrf_token: str
    username: str
    roles: list[str]
    is_admin: bool
    created_at: datetime
    last_seen: datetime

    # The live TestBench connection (see module docstring). None only for
    # sessions built without one, e.g. in tests.
    tb_link: TestBenchLink | None = field(default=None, repr=False)

    # The TestBench user key, the identity the activity view filters on
    # (design D2). None when the login could not read it -- the user then
    # sees no own entries rather than anyone else's.
    user_key: str | None = None

    # The TestBench project list, fetched once inside the login connection and
    # cached here for the life of the session (design D3), so page loads never
    # cost a TestBench round-trip. ``projects_error`` records a
    # failed fetch without failing the login (D4) -- editing service, LLM and
    # logging settings must not depend on an unrelated TestBench endpoint.
    # ``POST /projects/refresh`` replaces all three.
    projects: list[ProjectRef] = field(default_factory=list)
    projects_fetched_at: datetime | None = None
    projects_error: str | None = None


class SessionStore:
    """In-memory sessions with an idle timeout and an absolute cap."""

    def __init__(
        self,
        idle_timeout: timedelta = IDLE_TIMEOUT,
        absolute_timeout: timedelta = ABSOLUTE_TIMEOUT,
        now: Callable[[], datetime] = _utcnow,
    ):
        self._sessions: dict[str, Session] = {}
        self._idle_timeout = idle_timeout
        self._absolute_timeout = absolute_timeout
        self._now = now

    def create(
        self,
        username: str,
        roles: list[str],
        is_admin: bool,
        tb_link: TestBenchLink | None = None,
        user_key: str | None = None,
    ) -> Session:
        moment = self._now()
        self._sweep(moment)
        session = Session(
            sid=secrets.token_urlsafe(32),
            csrf_token=secrets.token_urlsafe(32),
            username=username,
            roles=roles,
            is_admin=is_admin,
            tb_link=tb_link,
            created_at=moment,
            last_seen=moment,
            user_key=user_key,
        )
        self._sessions[session.sid] = session
        return session

    def get(self, sid: str | None) -> Session | None:
        """Return the live session for *sid*, refreshing its idle timer.

        An expired session is discarded rather than merely hidden.
        """
        if not sid:
            return None
        session = self._sessions.get(sid)
        if session is None:
            return None

        moment = self._now()
        if self._is_expired(session, moment):
            self.revoke(sid)
            return None

        session.last_seen = moment
        return session

    def revoke(self, sid: str) -> None:
        session = self._sessions.pop(sid, None)
        if session is not None and session.tb_link is not None:
            session.tb_link.close()

    def close_all(self) -> None:
        """End every session; for service shutdown."""
        for sid in list(self._sessions):
            self.revoke(sid)

    def _is_expired(self, session: Session, moment: datetime) -> bool:
        return (
            moment - session.last_seen > self._idle_timeout
            or moment - session.created_at > self._absolute_timeout
        )

    def _sweep(self, moment: datetime) -> None:
        """Drop every expired session, not just the one being looked up.

        A session whose browser never comes back is otherwise never looked up
        again, and its link would keep a heartbeat thread pinging TestBench
        for as long as the process runs.
        """
        for sid, session in list(self._sessions.items()):
            if self._is_expired(session, moment):
                self.revoke(sid)
