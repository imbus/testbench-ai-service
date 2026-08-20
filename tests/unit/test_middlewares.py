import logging
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from testbench_ai_service.log import VERBOSE, logger
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
        calls = [str(c) for c in mock_logger.log.call_args_list]
        assert any("Request Body" in c for c in calls)

    @patch("testbench_ai_service.middlewares.logger")
    def test_post_body_is_logged_with_the_api_key_redacted(self, mock_logger):
        app = FastAPI()
        app.add_middleware(LoggingMiddleware)

        @app.post("/agent")
        async def agent():
            return {"ok": True}

        client = TestClient(app)
        client.post("/agent", json={"llm_config": {"model": "gpt-4o", "api_key": "sk-abc123"}})

        messages = _rendered_payloads(mock_logger)
        assert any('"api_key": "***"' in m for m in messages)
        assert not any("sk-abc123" in m for m in messages)


def _rendered(mock_logger):
    """Render each debug call the way the handler would, so assertions see the body."""
    messages = []
    for call in mock_logger.debug.call_args_list:
        message = call.args[0]
        messages.append(message % call.args[1:] if len(call.args) > 1 else message)
    return messages


def _rendered_payloads(mock_logger):
    """Render each VERBOSE payload call; logger.log puts the level in args[0]."""
    messages = []
    for call in mock_logger.log.call_args_list:
        message = call.args[1]
        messages.append(message % call.args[2:] if len(call.args) > 2 else message)
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

        messages = _rendered_payloads(mock_logger)
        assert any(
            'Testbench request body: {"login": "tbadmin", "password": "***"}' in m for m in messages
        )
        assert not any("hunter2" in m for m in messages)

    @patch("testbench_ai_service.middlewares.logger")
    def test_raw_data_body_logs_a_size_placeholder_only(self, mock_logger):
        request = MagicMock(return_value=MagicMock(status_code=200))

        _log_outbound(request, data=b"PK\x03\x04binary", json=None)

        messages = _rendered_payloads(mock_logger)
        assert any("Testbench request body: <non-JSON body, 10 bytes>" in m for m in messages)
        assert not any("PK" in m for m in messages)

    @patch("testbench_ai_service.middlewares.logger")
    def test_body_without_a_length_reports_unknown_size(self, mock_logger):
        request = MagicMock(return_value=MagicMock(status_code=200))
        handle = MagicMock(spec=[])  # no __len__

        _log_outbound(request, data=handle, json=None)

        messages = _rendered_payloads(mock_logger)
        assert any("<non-JSON body, size unknown>" in m for m in messages)

    @patch("testbench_ai_service.middlewares.logger")
    def test_bodyless_request_logs_no_body_line(self, mock_logger):
        request = MagicMock(return_value=MagicMock(status_code=200))

        _log_outbound(request, method="GET")

        assert not any("request body" in m for m in _rendered_payloads(mock_logger))

    @patch("testbench_ai_service.middlewares.logger")
    def test_response_body_is_logged_at_verbose(self, mock_logger):
        response = MagicMock(status_code=200, text='{"key": "TCS-1"}')
        response.headers = {"Content-Type": "application/vnd.testbench+json"}
        request = MagicMock(return_value=response)

        _log_outbound(request, method="GET")

        messages = _rendered_payloads(mock_logger)
        assert any('Testbench response body: {"key": "TCS-1"}' in m for m in messages)

    @patch("testbench_ai_service.middlewares.logger")
    def test_response_body_secrets_are_redacted(self, mock_logger):
        response = MagicMock(status_code=200, text='{"sessionToken": "abc123"}')
        response.headers = {"Content-Type": "application/json"}
        request = MagicMock(return_value=response)

        _log_outbound(request, method="POST")

        messages = _rendered_payloads(mock_logger)
        assert any('"sessionToken": "***"' in m for m in messages)
        assert not any("abc123" in m for m in messages)

    @patch("testbench_ai_service.middlewares.logger")
    def test_binary_response_body_logs_a_size_placeholder_only(self, mock_logger):
        """The JSON report download returns a zip; it must never be dumped into the log."""
        response = MagicMock(status_code=200, text="PK\x03\x04binary")
        response.headers = {"Content-Type": "application/zip"}
        response.content = b"PK\x03\x04binary"
        request = MagicMock(return_value=response)

        _log_outbound(request, method="GET")

        messages = _rendered_payloads(mock_logger)
        assert any("Testbench response body: <non-text body, 10 bytes>" in m for m in messages)
        assert not any("PK" in m for m in messages)

    def test_no_payload_is_logged_when_verbose_is_off(self):
        """At DEBUG the outbound call still runs, but neither body reaches the log."""
        with patch("testbench_ai_service.middlewares.logger") as mock_logger:
            mock_logger.isEnabledFor.return_value = False
            response = MagicMock(status_code=200, text='{"sessionToken": "abc123"}')
            response.headers = {"Content-Type": "application/json"}
            request = MagicMock(return_value=response)

            _log_outbound(request, json={"login": "tbadmin", "password": "hunter2"})

        assert not mock_logger.log.called
        assert any(
            "Testbench request:" in call.args[0] for call in mock_logger.debug.call_args_list
        )


class TestInboundPayloadLogging:
    """Inbound request and response payloads are logged only when a sink asks for VERBOSE."""

    @pytest.fixture(autouse=True)
    def capture(self):
        self.stream = StringIO()
        self.handler = logging.StreamHandler(self.stream)
        self.handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        self.original_level = logger.level
        logger.addHandler(self.handler)
        yield
        logger.removeHandler(self.handler)
        self.handler.close()
        logger.setLevel(self.original_level)

    @property
    def output(self) -> str:
        self.handler.flush()
        return str(self.stream.getvalue())

    def _client(self, max_payload_length: int = 4000) -> TestClient:
        app = FastAPI()
        app.add_middleware(LoggingMiddleware, max_payload_length=max_payload_length)

        @app.post("/echo")
        async def echo(payload: dict):
            return payload

        return TestClient(app)

    def test_request_payload_is_logged_at_verbose(self):
        logger.setLevel(VERBOSE)
        self._client().post("/echo", json={"ingredient": "cinnamon"})
        assert "cinnamon" in self.output

    def test_response_payload_is_logged_at_verbose(self):
        logger.setLevel(VERBOSE)
        self._client().post("/echo", json={"answer": "42"})
        assert "Response Body" in self.output

    def test_payloads_are_not_logged_at_debug(self):
        """DEBUG must stay usable without dumping payloads into the log."""
        logger.setLevel(logging.DEBUG)
        self._client().post("/echo", json={"ingredient": "cinnamon"})
        assert "cinnamon" not in self.output
        assert "Request:" in self.output

    def test_long_payload_is_truncated(self):
        logger.setLevel(VERBOSE)
        long_value = "x" * 500
        self._client(max_payload_length=50).post("/echo", json={"data": long_value})
        assert long_value not in self.output
        assert "truncated" in self.output

    def test_zero_max_payload_length_disables_truncation(self):
        logger.setLevel(VERBOSE)
        long_value = "x" * 500
        self._client(max_payload_length=0).post("/echo", json={"data": long_value})
        assert long_value in self.output

    def test_response_payload_secrets_are_redacted(self):
        logger.setLevel(VERBOSE)
        self._client().post("/echo", json={"sessionToken": "abc123"})
        assert "abc123" not in self.output

    def test_client_still_receives_the_full_response_body(self):
        """Consuming the response iterator to log it must not swallow the body."""
        logger.setLevel(VERBOSE)
        response = self._client().post("/echo", json={"answer": "42"})
        assert response.json() == {"answer": "42"}
