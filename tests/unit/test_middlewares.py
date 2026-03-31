import unittest
from unittest.mock import patch

from fastapi import FastAPI
from starlette.testclient import TestClient

from testbench_ai_service.middlewares import LoggingMiddleware


class TestLoggingMiddleware(unittest.IsolatedAsyncioTestCase):
    """Tests for ``LoggingMiddleware``."""

    def _make_app(self):
        app = FastAPI()
        app.add_middleware(LoggingMiddleware)

        @app.get("/ping")
        def ping():
            return {"pong": True}

        return app

    def test_request_passes_through_and_returns_200(self):
        client = TestClient(self._make_app())
        response = client.get("/ping")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"pong": True})

    @patch("testbench_ai_service.middlewares.logger")
    def test_debug_log_is_called_for_each_request(self, mock_logger):
        client = TestClient(self._make_app())
        client.get("/ping")
        self.assertTrue(mock_logger.debug.called)

    @patch("testbench_ai_service.middlewares.logger")
    def test_post_request_logs_body(self, mock_logger):
        app = FastAPI()
        app.add_middleware(LoggingMiddleware)

        @app.post("/data")
        async def data():
            return {"ok": True}

        client = TestClient(app)
        client.post("/data", json={"key": "value"})
        # At least one debug call should mention the request body
        calls = [str(c) for c in mock_logger.debug.call_args_list]
        self.assertTrue(any("Request Body" in c for c in calls))


if __name__ == "__main__":
    unittest.main()
