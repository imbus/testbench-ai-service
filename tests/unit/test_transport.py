"""Unit tests for :mod:`testbench_ai_service.transport`."""

import contextlib
import socket
import struct
import threading
from unittest.mock import MagicMock

import pytest
import requests
from testbench_cli_reporter.testbench import Connection as TBConnection
from urllib3.exceptions import MaxRetryError, NewConnectionError, ProtocolError

from testbench_ai_service import transport
from testbench_ai_service.transport import (
    DEFAULT_CONNECT_TIMEOUT,
    DEFAULT_MAX_RETRIES,
    DEFAULT_READ_POST_ATTEMPTS,
    DEFAULT_READ_TIMEOUT,
    PLAY_DEFAULT_IDLE_TIMEOUT,
    ResilientHTTPAdapter,
    build_retry,
    harden_connection,
    retry_read_only_post,
)
from testbench_ai_service.utils.testbench import post_project_tov_structure

_OK_RESPONSE = (
    b"HTTP/1.1 200 OK\r\n"
    b"Content-Type: application/json\r\n"
    b"Content-Length: 2\r\n"
    b"Connection: keep-alive\r\n"
    b"\r\n"
    b"{}"
)


class TestResilientHTTPAdapter:
    """The adapter must add a default timeout without discarding explicit ones."""

    def test_default_timeout_applied_when_caller_passes_none(self, monkeypatch):
        adapter = ResilientHTTPAdapter(timeout=(3.0, 7.0))
        captured = {}
        monkeypatch.setattr(
            requests.adapters.HTTPAdapter,
            "send",
            lambda self, request, **kw: captured.update(kw) or MagicMock(),
        )

        adapter.send(MagicMock(), timeout=None)

        assert captured["timeout"] == (3.0, 7.0)

    def test_explicit_timeout_is_preserved(self, monkeypatch):
        """The connection's heartbeat passes ``(5, 10)`` and must keep it."""
        adapter = ResilientHTTPAdapter(timeout=(3.0, 7.0))
        captured = {}
        monkeypatch.setattr(
            requests.adapters.HTTPAdapter,
            "send",
            lambda self, request, **kw: captured.update(kw) or MagicMock(),
        )

        adapter.send(MagicMock(), timeout=(5, 10))

        assert captured["timeout"] == (5, 10)


class TestBuildRetry:
    """Retries must never replay a request the server may already have applied."""

    def test_retry_count_is_honoured(self):
        assert build_retry(4).total == 4

    def test_idempotent_methods_are_retried(self):
        allowed = build_retry(3).allowed_methods
        assert "GET" in allowed
        assert "PUT" in allowed
        assert "DELETE" in allowed

    def test_post_and_patch_are_not_retried(self):
        allowed = build_retry(3).allowed_methods
        assert "POST" not in allowed
        assert "PATCH" not in allowed

    def test_status_retries_disabled(self):
        assert build_retry(3).status == 0

    def test_zero_disables_retries(self):
        assert build_retry(0).total == 0


class TestHardenConnection:
    """``harden_connection`` re-mounts both schemes on the connection's session."""

    def test_mounts_resilient_adapter_for_both_schemes(self):
        conn = MagicMock()
        session = requests.Session()
        conn.session = session

        harden_connection(conn, connect_timeout=2.0, read_timeout=5.0, max_retries=2)

        for prefix in ("http://", "https://"):
            adapter = session.get_adapter(prefix + "example.invalid")
            assert isinstance(adapter, ResilientHTTPAdapter)
            assert adapter.timeout == (2.0, 5.0)
            assert adapter.max_retries.total == 2

    def test_uses_module_defaults(self):
        conn = MagicMock()
        session = requests.Session()
        conn.session = session

        harden_connection(conn)

        adapter = session.get_adapter("https://example.invalid")
        assert adapter.timeout == (DEFAULT_CONNECT_TIMEOUT, DEFAULT_READ_TIMEOUT)
        assert adapter.max_retries.total == DEFAULT_MAX_RETRIES


class _ConnectionResettingServer:
    """Serves one request per connection, then resets the next one it receives.

    Reproduces the failure behind ``WinError 10054`` / ``ECONNRESET``: the peer accepts
    a request on a pooled keep-alive connection and tears the socket down instead of
    answering.
    """

    def __init__(self, serve_ok: int = 1) -> None:
        self.serve_ok = serve_ok
        self.resets = 0
        self.connections = 0
        self._sock = socket.socket()
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(8)
        self.port = self._sock.getsockname()[1]
        self._stop = threading.Event()
        threading.Thread(target=self._accept_loop, daemon=True).start()

    def _accept_loop(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _ = self._sock.accept()
            except OSError:
                return
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn: socket.socket) -> None:
        self.connections += 1
        served = 0
        try:
            while True:
                request = b""
                while b"\r\n\r\n" not in request:
                    chunk = conn.recv(4096)
                    if not chunk:
                        return
                    request += chunk
                if served >= self.serve_ok:
                    self.resets += 1
                    conn.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
                    conn.close()
                    return
                conn.sendall(_OK_RESPONSE)
                served += 1
        except OSError:
            return

    def close(self) -> None:
        self._stop.set()
        with contextlib.suppress(OSError):
            self._sock.close()


@pytest.fixture
def resetting_server():
    server = _ConnectionResettingServer()
    yield server
    server.close()


class TestConnectionResetRecovery:
    """Regression tests for the dropped-keep-alive failure mode."""

    def _session(self, max_retries: int) -> requests.Session:
        session = requests.Session()
        # Loopback traffic must not be routed through a proxy configured in the
        # environment or in the Windows internet settings.
        session.trust_env = False
        adapter = ResilientHTTPAdapter(timeout=(2.0, 5.0), max_retries=build_retry(max_retries))
        session.mount("http://", adapter)
        return session

    def test_reset_without_retries_raises_connection_error(self, resetting_server):
        session = self._session(max_retries=0)
        base = f"http://127.0.0.1:{resetting_server.port}/api/2/projects/1"

        session.get(base)
        with pytest.raises(requests.exceptions.ConnectionError):
            session.get(f"{base}/testCaseSets/2")

        assert resetting_server.resets == 1
        session.close()

    def test_reset_is_retried_on_a_fresh_connection(self, resetting_server):
        session = self._session(max_retries=DEFAULT_MAX_RETRIES)
        base = f"http://127.0.0.1:{resetting_server.port}/api/2/projects/1"

        session.get(base)
        response = session.get(f"{base}/testCaseSets/2")

        assert response.status_code == 200
        assert resetting_server.resets == 1
        assert resetting_server.connections == 2
        session.close()


class _BootstrapStallingServer:
    """Answers the server-version probe, then stalls on the next request.

    Mirrors the bootstrap sequence of ``testbench_cli_reporter``'s ``Connection.session``:
    ``read_server_version`` runs first, then ``read_user_roles`` - the latter on the
    library's own ``TimeoutHTTPAdapter``, whose timeout is ``None`` unless
    ``connection_timeout_sec`` is passed to the constructor.
    """

    def __init__(self) -> None:
        self.stalled = threading.Event()
        self._sock = socket.socket()
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(8)
        self.port = self._sock.getsockname()[1]
        self._stop = threading.Event()
        self._held: list[socket.socket] = []
        threading.Thread(target=self._accept_loop, daemon=True).start()

    def _accept_loop(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _ = self._sock.accept()
            except OSError:
                return
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn: socket.socket) -> None:
        try:
            while True:
                request = b""
                while b"\r\n\r\n" not in request:
                    chunk = conn.recv(4096)
                    if not chunk:
                        return
                    request += chunk
                if b"serverVersions" in request:
                    body = b'{"version": "4.1.0"}'
                    conn.sendall(
                        b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                        b"Content-Length: " + str(len(body)).encode() + b"\r\n"
                        b"Connection: keep-alive\r\n\r\n" + body
                    )
                    continue
                # Any later request (read_user_roles) is accepted and never answered.
                self._held.append(conn)
                self.stalled.set()
                self._stop.wait()
                return
        except OSError:
            return

    def close(self) -> None:
        self._stop.set()
        for held in self._held:
            with contextlib.suppress(OSError):
                held.close()
        with contextlib.suppress(OSError):
            self._sock.close()


@pytest.fixture
def stalling_server():
    server = _BootstrapStallingServer()
    yield server
    server.close()


class TestBootstrapTimeout:
    """``connection_timeout_sec`` is what bounds the library's own bootstrap requests."""

    def _open_session(self, port: int, connection_timeout_sec, wait: float = 20):
        """Access ``conn.session`` in a thread; return (finished, raised exception)."""
        conn = TBConnection(
            f"http://127.0.0.1:{port}/api/",
            verify=False,
            sessionToken="tok",
            connection_timeout_sec=connection_timeout_sec,
        )
        outcome: dict = {}

        def _access():
            try:
                conn.session  # noqa: B018 - the property performs the bootstrap
            except BaseException as exc:  # recorded so the assertion can inspect it
                outcome["error"] = exc

        thread = threading.Thread(target=_access, daemon=True)
        thread.start()
        thread.join(timeout=wait)
        return not thread.is_alive(), outcome.get("error")

    def test_bootstrap_hangs_without_a_connection_timeout(self, stalling_server):
        """Without the timeout the stalled request never returns - the bug behind F1."""
        finished, _ = self._open_session(stalling_server.port, None, wait=5)

        assert stalling_server.stalled.wait(timeout=5)
        assert not finished, "expected the bootstrap to hang with connection_timeout_sec=None"

    def test_bootstrap_is_bounded_when_a_connection_timeout_is_given(self, stalling_server):
        finished, error = self._open_session(stalling_server.port, 2)

        assert finished, "expected the bootstrap to give up rather than hang"
        assert isinstance(error, requests.exceptions.Timeout)


def _peer_reset() -> requests.exceptions.ConnectionError:
    """The exception shape a Play idle-timeout produces on Windows.

    WSAECONNRESET (10054) inside a ``ProtocolError`` inside a ``ConnectionError``.
    """
    reset = ConnectionResetError(
        10054, "Eine vorhandene Verbindung wurde vom Remotehost geschlossen"
    )
    return requests.exceptions.ConnectionError(ProtocolError("Connection aborted.", reset))


class TestRetryReadOnlyPost:
    """``retry_read_only_post`` covers the gap urllib3's adapter policy leaves open.

    ``build_retry`` keeps ``POST`` out of ``allowed_methods`` so a specification
    ``PATCH`` is never replayed.  The structure endpoints are reads that happen to be
    spelled ``POST``, so they fall through that policy and reach the caller on the very
    first idle-timeout reset - which is exactly the failure this decorator absorbs.
    """

    @staticmethod
    def _no_sleeping(monkeypatch) -> list[float]:
        delays: list[float] = []
        monkeypatch.setattr(transport.time, "sleep", delays.append)
        return delays

    def test_reset_is_retried_and_the_second_attempt_wins(self, monkeypatch):
        """The observed recovery: a 75 s reset, then the same call succeeding in 1.5 s."""
        self._no_sleeping(monkeypatch)
        calls = []

        @retry_read_only_post()
        def structure():
            calls.append(1)
            if len(calls) == 1:
                raise _peer_reset()
            return "tree"

        assert structure() == "tree"
        assert len(calls) == 2

    def test_read_timeout_is_retried(self, monkeypatch):
        """Our own read timeout means the same thing: no response was produced."""
        self._no_sleeping(monkeypatch)
        calls = []

        @retry_read_only_post()
        def structure():
            calls.append(1)
            if len(calls) == 1:
                raise requests.exceptions.ReadTimeout("timed out")
            return "tree"

        assert structure() == "tree"
        assert len(calls) == 2

    def test_gives_up_after_the_configured_attempts(self, monkeypatch):
        self._no_sleeping(monkeypatch)
        calls = []

        @retry_read_only_post(attempts=3)
        def structure():
            calls.append(1)
            raise _peer_reset()

        with pytest.raises(requests.exceptions.ConnectionError):
            structure()
        assert len(calls) == 3, "expected exactly three attempts, not three retries"

    def test_backoff_grows_exponentially(self, monkeypatch):
        delays = self._no_sleeping(monkeypatch)

        @retry_read_only_post(attempts=3, backoff_factor=0.5)
        def structure():
            raise _peer_reset()

        with pytest.raises(requests.exceptions.ConnectionError):
            structure()
        assert delays == [0.5, 1.0]

    def test_unreachable_server_is_not_retried_here(self, monkeypatch):
        """``connect`` retries are not method-gated, so the adapter already handles them.

        Retrying again at the call site would multiply the adapter's attempts.
        """
        self._no_sleeping(monkeypatch)
        calls = []
        unreachable = requests.exceptions.ConnectionError(
            MaxRetryError(
                None,
                "https://tb:9443/api/",
                reason=NewConnectionError(None, "Failed to establish a new connection"),
            )
        )

        @retry_read_only_post()
        def structure():
            calls.append(1)
            raise unreachable

        with pytest.raises(requests.exceptions.ConnectionError):
            structure()
        assert len(calls) == 1

    def test_http_errors_are_not_retried(self, monkeypatch):
        """A 4xx/5xx is an answer.  Replaying it would just repeat the same answer."""
        self._no_sleeping(monkeypatch)
        calls = []

        @retry_read_only_post()
        def structure():
            calls.append(1)
            raise requests.exceptions.HTTPError("403 Forbidden")

        with pytest.raises(requests.exceptions.HTTPError):
            structure()
        assert len(calls) == 1

    def test_wrapper_keeps_the_wrapped_identity(self):
        @retry_read_only_post()
        def structure():
            """Docstring kept."""

        assert structure.__name__ == "structure"
        assert structure.__doc__ == "Docstring kept."


class TestReadTimeoutDefault:
    """The default must stay below the TestBench web server's own socket limit."""

    def test_default_read_timeout_is_below_the_play_idle_timeout(self):
        """Play's ``idleTimeout`` default is 75 s and TestBench ships it unchanged.

        A read timeout at or above that can never fire first, so a stalled request
        surfaces as the peer's reset instead of a timeout that names itself.
        """
        assert DEFAULT_READ_TIMEOUT < PLAY_DEFAULT_IDLE_TIMEOUT


_STRUCTURE_BODY = b'{"root": null, "nodes": []}'
_STRUCTURE_RESPONSE = (
    b"HTTP/1.1 200 OK\r\n"
    b"Content-Type: application/json\r\n"
    b"Content-Length: %d\r\n"
    b"Connection: keep-alive\r\n"
    b"\r\n" % len(_STRUCTURE_BODY)
) + _STRUCTURE_BODY


class _ResetsFirstRequestsServer:
    """Resets the first *resets_first* requests it receives, then answers normally.

    ``_ConnectionResettingServer`` counts per connection, which cannot express "the
    server was stalled a moment ago and is fine now" - the shape of the Play idle
    timeout, where a retry on a fresh connection is what succeeds.
    """

    def __init__(self, resets_first: int = 1) -> None:
        self.resets_first = resets_first
        self.requests_seen = 0
        self._lock = threading.Lock()
        self._sock = socket.socket()
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(8)
        self.port = self._sock.getsockname()[1]
        self._stop = threading.Event()
        threading.Thread(target=self._accept_loop, daemon=True).start()

    def _accept_loop(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _ = self._sock.accept()
            except OSError:
                return
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn: socket.socket) -> None:
        try:
            while True:
                request = b""
                while b"\r\n\r\n" not in request:
                    chunk = conn.recv(4096)
                    if not chunk:
                        return
                    request += chunk
                header, _, rest = request.partition(b"\r\n\r\n")
                length = 0
                for line in header.split(b"\r\n"):
                    if line.lower().startswith(b"content-length:"):
                        length = int(line.split(b":")[1])
                while len(rest) < length:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    rest += chunk
                with self._lock:
                    self.requests_seen += 1
                    should_reset = self.requests_seen <= self.resets_first
                if should_reset:
                    conn.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
                    conn.close()
                    return
                conn.sendall(_STRUCTURE_RESPONSE)
        except OSError:
            return

    def close(self) -> None:
        self._stop.set()
        with contextlib.suppress(OSError):
            self._sock.close()


@pytest.fixture
def stalling_then_healthy_server():
    server = _ResetsFirstRequestsServer()
    yield server
    server.close()


class TestStructureRetryEndToEnd:
    """The whole chain, over a real socket: reset -> retry -> tree.

    The unit tests above drive the decorator with synthetic exceptions.  This one proves
    the exception a real reset produces is actually recognised by
    ``_response_never_arrived`` once ``requests`` and ``urllib3`` are done wrapping it.
    """

    def test_structure_post_survives_a_reset(self, monkeypatch, stalling_then_healthy_server):
        monkeypatch.setattr(transport.time, "sleep", lambda _: None)
        session = requests.Session()
        session.trust_env = False
        session.mount(
            "http://",
            ResilientHTTPAdapter(timeout=(2.0, 5.0), max_retries=build_retry(DEFAULT_MAX_RETRIES)),
        )
        conn = MagicMock()
        conn.server_url = f"http://127.0.0.1:{stalling_then_healthy_server.port}/api/"
        conn.session = session

        tree = post_project_tov_structure(conn, "310023", "230013")

        assert tree.nodes == []
        assert stalling_then_healthy_server.requests_seen == 2
        session.close()

    def test_structure_post_still_fails_when_the_server_never_recovers(
        self, monkeypatch, stalling_then_healthy_server
    ):
        """Retrying must not turn a genuinely broken server into a silent success."""
        monkeypatch.setattr(transport.time, "sleep", lambda _: None)
        stalling_then_healthy_server.resets_first = 99
        session = requests.Session()
        session.trust_env = False
        session.mount(
            "http://", ResilientHTTPAdapter(timeout=(2.0, 5.0), max_retries=build_retry(0))
        )
        conn = MagicMock()
        conn.server_url = f"http://127.0.0.1:{stalling_then_healthy_server.port}/api/"
        conn.session = session

        with pytest.raises(requests.exceptions.ConnectionError):
            post_project_tov_structure(conn, "310023", "230013")

        assert stalling_then_healthy_server.requests_seen == DEFAULT_READ_POST_ATTEMPTS
        session.close()
