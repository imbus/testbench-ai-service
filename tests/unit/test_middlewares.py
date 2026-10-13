import json
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from starlette.testclient import TestClient

from testbench_ai_service.middlewares import (
    LoggingMiddleware,
    OutboundRequestLoggingMiddleware,
    redact_body,
)


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


class TestRedactBody:
    def test_login_body_is_never_logged(self):
        body = json.dumps({"username": "a", "password": "geheim"})
        assert redact_body("/admin/api/session", body) == "<redacted>"

    def test_sensitive_keys_are_masked_recursively(self):
        body = json.dumps(
            {"edits": {"llm": {"OPENAI_API_KEY": "sk-1", "model": "x"}}, "items": [{"token": "t"}]}
        )
        out = json.loads(redact_body("/admin/api/config/apply", body))
        assert out["edits"]["llm"]["OPENAI_API_KEY"] == "<redacted>"
        assert out["edits"]["llm"]["model"] == "x"
        assert out["items"][0]["token"] == "<redacted>"

    def test_non_json_body_is_returned_unchanged(self):
        assert redact_body("/x", "plain text") == "plain text"


class TestLoggingMiddlewareRedaction:
    @patch("testbench_ai_service.middlewares.logger")
    def test_login_password_never_reaches_the_log(self, mock_logger):
        app = FastAPI()
        app.add_middleware(LoggingMiddleware)

        @app.post("/admin/api/session")
        async def login():
            return {"ok": True}

        TestClient(app).post("/admin/api/session", json={"username": "a", "password": "geheim"})
        logged = " ".join(str(c) for c in mock_logger.debug.call_args_list)
        assert "geheim" not in logged
