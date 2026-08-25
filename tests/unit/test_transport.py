"""Unit tests for :mod:`testbench_ai_service.transport`."""

import contextlib
import socket
import struct
import threading
from unittest.mock import MagicMock

import pytest
import requests

from testbench_ai_service.transport import (
    DEFAULT_CONNECT_TIMEOUT,
    DEFAULT_MAX_RETRIES,
    DEFAULT_READ_TIMEOUT,
    ResilientHTTPAdapter,
    build_retry,
    harden_connection,
)

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
