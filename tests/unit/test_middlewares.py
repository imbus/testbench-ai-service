import json
import logging
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, Request, Response
from starlette.testclient import TestClient

from testbench_ai_service.log import LogContextFilter, log_in_request
from testbench_ai_service.log import logger as service_logger
from testbench_ai_service.middlewares import (
    MAX_LOGGED_BODY,
    LoggingMiddleware,
    OutboundRequestLoggingMiddleware,
    RequestScopeMiddleware,
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

    def test_key_spellings_of_credentials_are_masked(self):
        body = json.dumps(
            {"apiKey": "sk-1", "x-api-key": "sk-2", "credential": "c", "Authorization": "Bearer b"}
        )
        out = json.loads(redact_body("/x", body))
        assert set(out.values()) == {"<redacted>"}

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


def _debug_lines(mock_logger) -> list[str]:
    return [str(call.args[0]) for call in mock_logger.debug.call_args_list]


class TestLoggingMiddlewareBodies:
    """Only text a reader can use is written to the log (console assets, uploads are not)."""

    @staticmethod
    def _app() -> FastAPI:
        app = FastAPI()
        app.add_middleware(LoggingMiddleware)

        @app.get("/asset.js")
        async def asset():
            return Response("const secret = 'bundle-content'", media_type="text/javascript")

        @app.get("/font.woff2")
        async def font():
            return Response(b"wOF2" + bytes(range(256)), media_type="font/woff2")

        @app.get("/big")
        async def big():
            return {"data": "x" * (MAX_LOGGED_BODY * 2)}

        @app.post("/upload")
        async def upload(request: Request):
            return {"size": len(await request.body())}

        return app

    @patch("testbench_ai_service.middlewares.logger")
    def test_a_script_is_named_but_not_logged(self, mock_logger):
        response = TestClient(self._app()).get("/asset.js")

        assert response.text == "const secret = 'bundle-content'"
        lines = _debug_lines(mock_logger)
        assert "Response Body: <text/javascript, 31 bytes, not logged>" in lines
        assert not any("bundle-content" in line for line in lines)

    @patch("testbench_ai_service.middlewares.logger")
    def test_a_binary_file_reaches_the_client_whole_and_is_not_logged(self, mock_logger):
        response = TestClient(self._app()).get("/font.woff2")

        assert response.content == b"wOF2" + bytes(range(256))
        assert not any("wOF2" in line for line in _debug_lines(mock_logger))

    @patch("testbench_ai_service.middlewares.logger")
    def test_a_json_response_is_still_logged(self, mock_logger):
        TestClient(_make_app()).get("/ping")

        assert 'Response Body: {"pong": true}' in _debug_lines(mock_logger)

    @patch("testbench_ai_service.middlewares.logger")
    def test_a_long_json_response_is_shortened_in_the_log_only(self, mock_logger):
        response = TestClient(self._app()).get("/big")

        assert len(response.json()["data"]) == MAX_LOGGED_BODY * 2
        body = next(line for line in _debug_lines(mock_logger) if line.startswith("Response Body"))
        assert len(body) < MAX_LOGGED_BODY + 200
        assert "shortened" in body

    @patch("testbench_ai_service.middlewares.logger")
    def test_an_uploaded_file_is_named_but_not_logged(self, mock_logger):
        response = TestClient(self._app()).post(
            "/upload", files={"file": ("a.whl", b"PK-wheel-bytes", "application/octet-stream")}
        )

        assert response.json()["size"] > len(b"PK-wheel-bytes")
        lines = _debug_lines(mock_logger)
        assert any(
            line.startswith("Request Body: <multipart/form-data, ") and "not logged" in line
            for line in lines
        )
        assert not any("PK-wheel-bytes" in line for line in lines)


class _Capture(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.records: list[logging.LogRecord] = []
        self.addFilter(LogContextFilter())

    def emit(self, record):
        self.records.append(record)


@pytest.fixture
def capture():
    handler = _Capture()
    previous = service_logger.level
    service_logger.setLevel(logging.DEBUG)
    service_logger.addHandler(handler)
    yield handler
    service_logger.removeHandler(handler)
    service_logger.setLevel(previous)


class TestRequestScopeMiddleware:
    def test_records_inside_a_request_are_request_scoped(self, capture):
        app = FastAPI()
        app.add_middleware(LoggingMiddleware)
        app.add_middleware(RequestScopeMiddleware)  # added last = outermost

        @app.post("/x")
        async def x():
            service_logger.info("inside")
            return {"ok": True}

        TestClient(app).post("/x", json={"a": 1})
        assert capture.records
        assert {r.scope for r in capture.records} == {"request"}

    def test_records_outside_a_request_stay_service(self, capture):
        service_logger.info("startup")
        assert capture.records[-1].scope == "service"

    async def test_marker_survives_the_app_returning(self):
        # Review Focus 1: uvicorn logs an unhandled exception after the app
        # returns, in the same task. That record must still be request-scoped.
        async def failing_app(scope, receive, send):
            raise RuntimeError("boom")

        middleware = RequestScopeMiddleware(failing_app)
        with pytest.raises(RuntimeError):
            await middleware({"type": "http"}, None, None)
        try:
            assert log_in_request.get() is True
        finally:
            log_in_request.set(False)

    async def test_lifespan_is_not_marked(self):
        async def app(scope, receive, send):
            assert log_in_request.get() is False

        await RequestScopeMiddleware(app)({"type": "lifespan"}, None, None)

    async def test_websocket_is_marked(self):
        seen = []

        async def app(scope, receive, send):
            seen.append(log_in_request.get())

        try:
            await RequestScopeMiddleware(app)({"type": "websocket"}, None, None)
        finally:
            log_in_request.set(False)
        assert seen == [True]
