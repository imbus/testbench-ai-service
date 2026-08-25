from unittest.mock import MagicMock, patch

import pytest
import requests
from fastapi import FastAPI, HTTPException
from starlette.testclient import TestClient
from urllib3.exceptions import ProtocolError

from testbench_ai_service.exceptions import (
    ELAPSED_ATTRIBUTE,
    handle_requests_transport_error,
)
from testbench_ai_service.middlewares import LoggingMiddleware, OutboundRequestLoggingMiddleware


def _make_app():
    app = FastAPI()
    app.add_middleware(LoggingMiddleware)

    @app.get("/ping")
    def ping():
        return {"pong": True}

    return app


class TestLoggingMiddleware:
    """Tests for ``LoggingMiddleware``."""

    def test_request_passes_through_and_returns_200(self):
        client = TestClient(_make_app())
        response = client.get("/ping")
        assert response.status_code == 200
        assert response.json() == {"pong": True}

    @patch("testbench_ai_service.middlewares.logger")
    def test_debug_log_is_called_for_each_request(self, mock_logger):
        client = TestClient(_make_app())
        client.get("/ping")
        assert mock_logger.debug.called

    @patch("testbench_ai_service.middlewares.logger")
    def test_post_request_logs_body(self, mock_logger):
        app = FastAPI()
        app.add_middleware(LoggingMiddleware)

        @app.post("/data")
        async def data():
            return {"ok": True}

        client = TestClient(app)
        client.post("/data", json={"key": "value"})
        calls = [str(c) for c in mock_logger.debug.call_args_list]
        assert any("Request Body" in c for c in calls)


class TestOutboundRequestLoggingMiddleware:
    @patch("testbench_ai_service.middlewares.logger")
    def test_logs_testbench_request_response_and_duration(self, mock_logger):
        original_urls = OutboundRequestLoggingMiddleware._testbench_server_urls.copy()
        OutboundRequestLoggingMiddleware._testbench_server_urls = {"https://testbench.example/api"}
        response = MagicMock(status_code=200)
        request = MagicMock(return_value=response)

        try:
            result = OutboundRequestLoggingMiddleware._log_testbench_request(
                request,
                MagicMock(),
                "GET",
                "https://testbench.example/api/projects?token=secret",
            )
        finally:
            OutboundRequestLoggingMiddleware._testbench_server_urls = original_urls

        assert result is response
        request.assert_called_once()
        log_messages = [call.args[0] for call in mock_logger.debug.call_args_list]
        assert any("Testbench request:" in message for message in log_messages)
        assert any("Testbench response:" in message for message in log_messages)


class TestElapsedTimeReachesTheErrorMessage:
    """The join between the outbound logger and the 502 detail.

    Each side is unit-tested on its own; this covers the hand-off between them, which is
    the part that silently degrades to "no duration" if either end is renamed.
    """

    def test_a_failed_call_carries_its_duration_into_the_502(self, monkeypatch):
        server_url = "https://tb:9443/api/"
        OutboundRequestLoggingMiddleware.install(server_url)

        def _boom(*args, **kwargs):
            raise requests.exceptions.ConnectionError(
                ProtocolError("Connection aborted.", ConnectionResetError(10054, "reset"))
            )

        monkeypatch.setattr(requests.adapters.HTTPAdapter, "send", _boom)

        session = requests.Session()
        session.trust_env = False
        with pytest.raises(requests.exceptions.ConnectionError) as raised:
            session.post(f"{server_url}2/projects/1/tovs/2/structure", json={})

        assert getattr(raised.value, ELAPSED_ATTRIBUTE, None) is not None

        with pytest.raises(HTTPException) as exc_info:
            handle_requests_transport_error(raised.value)
        assert "closed the connection before responding after" in exc_info.value.detail
