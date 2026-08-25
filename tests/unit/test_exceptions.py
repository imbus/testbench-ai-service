import json
from unittest.mock import MagicMock

import pytest
import requests
from fastapi import HTTPException

from testbench_ai_service.exceptions import (
    TRANSPORT_ERRORS,
    handle_requests_http_error,
    handle_requests_transport_error,
    http_exception_handler,
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
