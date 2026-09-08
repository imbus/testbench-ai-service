"""Server-side session store for the console.

The browser only ever receives an opaque session id.  The TestBench session
token stays here, so a stolen cookie cannot be replayed against TestBench.
Note that on TestBench 3, ``Connection.authenticate`` sets ``session_token``
to the user's plaintext password, so on those deployments the value stored
here is the password itself -- a disclosure of this store's memory yields
credentials, not merely a replayable token.

The store is process-local: restarting the service logs everyone out.
"""

import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

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
    tb_session_token: str = field(repr=False)
    created_at: datetime
    last_seen: datetime


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
        self, username: str, roles: list[str], is_admin: bool, tb_session_token: str
    ) -> Session:
        moment = self._now()
        session = Session(
            sid=secrets.token_urlsafe(32),
            csrf_token=secrets.token_urlsafe(32),
            username=username,
            roles=roles,
            is_admin=is_admin,
            tb_session_token=tb_session_token,
            created_at=moment,
            last_seen=moment,
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
        if (
            moment - session.last_seen > self._idle_timeout
            or moment - session.created_at > self._absolute_timeout
        ):
            del self._sessions[sid]
            return None

        session.last_seen = moment
        return session

    def revoke(self, sid: str) -> None:
        self._sessions.pop(sid, None)
