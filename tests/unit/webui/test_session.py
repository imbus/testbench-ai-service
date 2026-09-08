from datetime import datetime, timedelta, timezone

import pytest

from testbench_ai_service.webui.session import (
    ABSOLUTE_TIMEOUT,
    IDLE_TIMEOUT,
    SessionStore,
)


class Clock:
    def __init__(self):
        self.now = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, delta: timedelta):
        self.now += delta


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def store(clock: Clock) -> SessionStore:
    return SessionStore(now=clock)


def _create(store: SessionStore, is_admin: bool = True):
    return store.create(
        username="a.mueller",
        roles=["Administrator"] if is_admin else ["ProjectUser"],
        is_admin=is_admin,
        tb_session_token="tb-token-abc",
    )


def test_create_returns_retrievable_session(store: SessionStore):
    session = _create(store)
    assert store.get(session.sid) is session
    assert session.username == "a.mueller"
    assert session.is_admin is True


def test_sid_and_csrf_are_distinct_and_unguessable(store: SessionStore):
    session = _create(store)
    assert session.sid != session.csrf_token
    assert len(session.sid) >= 32
    assert len(session.csrf_token) >= 32


def test_sessions_are_unique(store: SessionStore):
    assert _create(store).sid != _create(store).sid


def test_get_unknown_sid_returns_none(store: SessionStore):
    assert store.get("nope") is None


def test_get_none_returns_none(store: SessionStore):
    assert store.get(None) is None


def test_revoke_removes_the_session(store: SessionStore):
    session = _create(store)
    store.revoke(session.sid)
    assert store.get(session.sid) is None


def test_revoke_is_idempotent(store: SessionStore):
    store.revoke("never-existed")


def test_expires_after_idle_timeout(store: SessionStore, clock: Clock):
    session = _create(store)
    clock.advance(IDLE_TIMEOUT + timedelta(seconds=1))
    assert store.get(session.sid) is None


def test_activity_refreshes_the_idle_timeout(store: SessionStore, clock: Clock):
    session = _create(store)
    for _ in range(4):
        clock.advance(IDLE_TIMEOUT - timedelta(minutes=1))
        assert store.get(session.sid) is not None


def test_absolute_cap_is_not_extended_by_activity(store: SessionStore, clock: Clock):
    """Activity refreshes the idle timer but must not extend the absolute cap.

    Every step is smaller than IDLE_TIMEOUT, so the idle check can never be what
    expires the session — only the absolute cap can.
    """
    session = _create(store)
    step = IDLE_TIMEOUT - timedelta(minutes=1)
    elapsed = timedelta()

    while elapsed + step < ABSOLUTE_TIMEOUT:
        clock.advance(step)
        elapsed += step
        assert store.get(session.sid) is not None, "cap fired early"

    clock.advance(step)
    assert store.get(session.sid) is None


def test_expired_session_is_dropped_not_merely_hidden(store: SessionStore, clock: Clock):
    session = _create(store)
    clock.advance(ABSOLUTE_TIMEOUT + timedelta(seconds=1))
    store.get(session.sid)
    assert session.sid not in store._sessions


def test_defaults_match_the_spec():
    # Constant-first form is what ruff's SIM300 requires for comparing constants.
    assert timedelta(minutes=60) == IDLE_TIMEOUT
    assert timedelta(hours=8) == ABSOLUTE_TIMEOUT
