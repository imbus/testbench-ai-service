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
