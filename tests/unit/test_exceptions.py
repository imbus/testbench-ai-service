import json
from unittest.mock import MagicMock

import pytest
import requests
from fastapi import HTTPException
from urllib3.exceptions import MaxRetryError, NewConnectionError, ProtocolError

from testbench_ai_service.exceptions import (
    TRANSPORT_ERRORS,
    handle_requests_http_error,
    handle_requests_transport_error,
    http_exception_handler,
    peer_closed_connection,
)


class TestHttpExceptionHandler:
    """Tests for ``http_exception_handler``."""

    async def test_body_allowed_status_returns_json_detail(self):
        request = MagicMock()
        exc = HTTPException(status_code=422, detail="Unprocessable")
        response = await http_exception_handler(request, exc)

        body = json.loads(response.body)
        assert response.status_code == 422
        assert body["detail"] == "Unprocessable"

    async def test_body_not_allowed_status_returns_empty_response(self):
        """Status 204 No Content must not carry a body."""
        request = MagicMock()
        exc = HTTPException(status_code=204, detail="No Content")
        response = await http_exception_handler(request, exc)
        assert response.status_code == 204
        assert not getattr(response, "body", b"")


class TestHandleRequestsHttpError:
    """Tests for ``handle_requests_http_error``."""

    def _make_error(self, status_code=None, message="Error"):
        mock_response = None
        if status_code is not None:
            mock_response = MagicMock()
            mock_response.status_code = status_code
            mock_response.json.return_value = {"message": message}
        return requests.exceptions.HTTPError("error", response=mock_response)

    def test_404_raises_http_exception_with_404(self):
        with pytest.raises(HTTPException) as exc_info:
            handle_requests_http_error(self._make_error(404, "Not found"))
        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Not found"

    def test_400_raises_http_exception_with_400(self):
        with pytest.raises(HTTPException) as exc_info:
            handle_requests_http_error(self._make_error(400, "Bad request"))
        assert exc_info.value.status_code == 400

    def test_500_raises_http_exception_with_500(self):
        with pytest.raises(HTTPException) as exc_info:
            handle_requests_http_error(self._make_error(500, "Server error"))
        assert exc_info.value.status_code == 500

    def test_none_response_raises_500(self):
        """When the error has no response, status should default to 500."""
        with pytest.raises(HTTPException) as exc_info:
            handle_requests_http_error(self._make_error(status_code=None))
        assert exc_info.value.status_code == 500

    def test_non_json_response_falls_back_to_response_text(self):
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.json.side_effect = ValueError("No JSON body")
        mock_response.text = "Forbidden"

        error = requests.exceptions.HTTPError("error", response=mock_response)
        with pytest.raises(HTTPException) as exc_info:
            handle_requests_http_error(error)

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == "Forbidden"


class TestHandleRequestsTransportError:
    """Tests for ``handle_requests_transport_error``."""

    def test_connection_error_raises_502(self):
        error = requests.exceptions.ConnectionError("Connection refused")
        with pytest.raises(HTTPException) as exc_info:
            handle_requests_transport_error(error)
        assert exc_info.value.status_code == 502
        assert "Could not connect to TestBench server" in exc_info.value.detail
        assert exc_info.value.__cause__ is error

    def test_read_timeout_raises_502(self):
        """A stalled read is a ``Timeout`` but not a ``ConnectionError``."""
        error = requests.exceptions.ReadTimeout("Read timed out. (read timeout=120)")
        with pytest.raises(HTTPException) as exc_info:
            handle_requests_transport_error(error)
        assert exc_info.value.status_code == 502
        assert "did not respond in time" in exc_info.value.detail

    def test_connect_timeout_raises_502(self):
        """``ConnectTimeout`` derives from both branches; it must not be ambiguous."""
        with pytest.raises(HTTPException) as exc_info:
            handle_requests_transport_error(requests.exceptions.ConnectTimeout("too slow"))
        assert exc_info.value.status_code == 502

    def test_transport_errors_covers_both_branches(self):
        assert issubclass(requests.exceptions.ReadTimeout, TRANSPORT_ERRORS)
        assert issubclass(requests.exceptions.ConnectionError, TRANSPORT_ERRORS)

    def test_peer_reset_is_not_reported_as_a_failure_to_connect(self):
        """A reset mid-request must not send the reader to the URL and TLS settings.

        This is the shape ``requests`` produces when TestBench accepts a POST, never
        answers, and drops the socket: WSAECONNRESET (Windows error 10054) inside a
        ``ProtocolError`` inside a ``ConnectionError``.
        """
        reset = ConnectionResetError(
            10054, "Eine vorhandene Verbindung wurde vom Remotehost geschlossen"
        )
        error = requests.exceptions.ConnectionError(ProtocolError("Connection aborted.", reset))
        with pytest.raises(HTTPException) as exc_info:
            handle_requests_transport_error(error)
        assert exc_info.value.status_code == 502
        assert "closed the connection before responding" in exc_info.value.detail
        assert "Could not connect" not in exc_info.value.detail
        assert exc_info.value.__cause__ is error

    def test_peer_reset_detected_through_retry_wrapper(self):
        """Repeated resets on an idempotent method arrive wrapped in ``MaxRetryError``."""
        reset = ConnectionResetError(10054, "connection reset by peer")
        error = requests.exceptions.ConnectionError(
            MaxRetryError(None, "https://tb:9443/api/", reason=ProtocolError("aborted", reset))
        )
        with pytest.raises(HTTPException) as exc_info:
            handle_requests_transport_error(error)
        assert "closed the connection before responding" in exc_info.value.detail

    def test_elapsed_time_is_reported_when_the_middleware_recorded_it(self):
        """The constant 75 s is the tell that this is a server-side timeout, not a blip.

        ``TestBenchRequestLogger`` already measures every outbound call, so the duration
        rides along on the exception rather than being timed a second time here.
        """
        error = requests.exceptions.ConnectionError(
            ProtocolError("Connection aborted.", ConnectionResetError(10054, "reset"))
        )
        error.testbench_elapsed_seconds = 75.115
        with pytest.raises(HTTPException) as exc_info:
            handle_requests_transport_error(error)
        assert "after 75.1s" in exc_info.value.detail

    def test_detail_is_unchanged_when_no_duration_was_recorded(self):
        """Calls made outside the logging middleware must not grow a bogus duration."""
        error = requests.exceptions.ConnectionError("boom")
        with pytest.raises(HTTPException) as exc_info:
            handle_requests_transport_error(error)
        assert "after" not in exc_info.value.detail

    def test_unreachable_server_still_reports_a_failure_to_connect(self):
        """``NewConnectionError`` means the socket was never established."""
        error = requests.exceptions.ConnectionError(
            MaxRetryError(
                None,
                "https://tb:9443/api/",
                reason=NewConnectionError(None, "Failed to establish a new connection"),
            )
        )
        with pytest.raises(HTTPException) as exc_info:
            handle_requests_transport_error(error)
        assert "Could not connect to TestBench server" in exc_info.value.detail

    def test_refused_connection_is_not_a_peer_close(self):
        """ECONNREFUSED happens before a connection exists, so it is not a reset."""
        error = requests.exceptions.ConnectionError(ConnectionRefusedError(10061, "refused"))
        with pytest.raises(HTTPException) as exc_info:
            handle_requests_transport_error(error)
        assert "Could not connect to TestBench server" in exc_info.value.detail


class TestPeerClosedConnection:
    """Tests for ``peer_closed_connection``."""

    @pytest.mark.parametrize(
        "cause",
        [ConnectionResetError(), ConnectionAbortedError(), BrokenPipeError()],
    )
    def test_detects_each_peer_close_errno(self, cause):
        assert peer_closed_connection(requests.exceptions.ConnectionError(cause)) is True

    @pytest.mark.parametrize("link", ["__cause__", "__context__"])
    def test_detects_cause_reachable_only_through_the_exception_chain(self, link):
        """A wrapper carrying a plain message leaves the chain as the only link."""
        error = requests.exceptions.ConnectionError("Connection aborted.")
        setattr(error, link, ConnectionResetError(10054, "reset"))
        assert peer_closed_connection(error) is True

    def test_plain_message_is_not_a_peer_close(self):
        assert peer_closed_connection(requests.exceptions.ConnectionError("nope")) is False

    def test_terminates_on_a_self_referential_cause_chain(self):
        """The chain is walked, so a cycle must not hang the error path."""
        first = requests.exceptions.ConnectionError("first")
        second = requests.exceptions.ConnectionError("second")
        first.__cause__ = second
        second.__cause__ = first
        assert peer_closed_connection(first) is False
