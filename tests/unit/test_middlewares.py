from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from starlette.testclient import TestClient

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


def _rendered(mock_logger):
    """Render each debug call the way the handler would, so assertions see the body."""
    messages = []
    for call in mock_logger.debug.call_args_list:
        message = call.args[0]
        messages.append(message % call.args[1:] if len(call.args) > 1 else message)
    return messages


def _log_outbound(mock_request, method="POST", **kwargs):
    original_urls = OutboundRequestLoggingMiddleware._testbench_server_urls.copy()
    OutboundRequestLoggingMiddleware._testbench_server_urls = {"https://testbench.example/api"}
    try:
        return OutboundRequestLoggingMiddleware._log_testbench_request(
            mock_request,
            MagicMock(),
            method,
            "https://testbench.example/api/2/login/session",
            **kwargs,
        )
    finally:
        OutboundRequestLoggingMiddleware._testbench_server_urls = original_urls


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

    @patch("testbench_ai_service.middlewares.logger")
    def test_json_body_is_logged_with_secrets_redacted(self, mock_logger):
        request = MagicMock(return_value=MagicMock(status_code=200))

        _log_outbound(request, data=None, json={"login": "tbadmin", "password": "hunter2"})

        messages = _rendered(mock_logger)
        assert any(
            'Testbench request body: {"login": "tbadmin", "password": "***"}' in m for m in messages
        )
        assert not any("hunter2" in m for m in messages)

    @patch("testbench_ai_service.middlewares.logger")
    def test_raw_data_body_logs_a_size_placeholder_only(self, mock_logger):
        request = MagicMock(return_value=MagicMock(status_code=200))

        _log_outbound(request, data=b"PK\x03\x04binary", json=None)

        messages = _rendered(mock_logger)
        assert any("Testbench request body: <non-JSON body, 10 bytes>" in m for m in messages)
        assert not any("PK" in m for m in messages)

    @patch("testbench_ai_service.middlewares.logger")
    def test_body_without_a_length_reports_unknown_size(self, mock_logger):
        request = MagicMock(return_value=MagicMock(status_code=200))
        handle = MagicMock(spec=[])  # no __len__

        _log_outbound(request, data=handle, json=None)

        messages = _rendered(mock_logger)
        assert any("<non-JSON body, size unknown>" in m for m in messages)

    @patch("testbench_ai_service.middlewares.logger")
    def test_bodyless_request_logs_no_body_line(self, mock_logger):
        request = MagicMock(return_value=MagicMock(status_code=200))

        _log_outbound(request, method="GET")

        assert not any("request body" in m for m in _rendered(mock_logger))
