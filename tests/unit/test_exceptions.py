import json
import unittest
from unittest.mock import MagicMock

import requests
from fastapi import HTTPException

from testbench_ai_service.exceptions import handle_requests_http_error, http_exception_handler


class TestHttpExceptionHandler(unittest.IsolatedAsyncioTestCase):
    """Tests for ``http_exception_handler``."""

    async def test_body_allowed_status_returns_json_detail(self):
        request = MagicMock()
        exc = HTTPException(status_code=422, detail="Unprocessable")
        response = await http_exception_handler(request, exc)

        body = json.loads(response.body)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(body["detail"], "Unprocessable")

    async def test_body_not_allowed_status_returns_empty_response(self):
        """Status 204 No Content must not carry a body."""
        request = MagicMock()
        exc = HTTPException(status_code=204, detail="No Content")
        response = await http_exception_handler(request, exc)
        self.assertEqual(response.status_code, 204)
        # Response body should be absent / empty
        self.assertFalse(getattr(response, "body", b""))


class TestHandleRequestsHttpError(unittest.TestCase):
    """Tests for ``handle_requests_http_error``."""

    def _make_error(self, status_code=None, message="Error"):
        mock_response = None
        if status_code is not None:
            mock_response = MagicMock()
            mock_response.status_code = status_code
            mock_response.json.return_value = {"message": message}
        return requests.exceptions.HTTPError("error", response=mock_response)

    def test_404_raises_http_exception_with_404(self):
        with self.assertRaises(HTTPException) as ctx:
            handle_requests_http_error(self._make_error(404, "Not found"))
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertEqual(ctx.exception.detail, "Not found")

    def test_400_raises_http_exception_with_400(self):
        with self.assertRaises(HTTPException) as ctx:
            handle_requests_http_error(self._make_error(400, "Bad request"))
        self.assertEqual(ctx.exception.status_code, 400)

    def test_500_raises_http_exception_with_500(self):
        with self.assertRaises(HTTPException) as ctx:
            handle_requests_http_error(self._make_error(500, "Server error"))
        self.assertEqual(ctx.exception.status_code, 500)

    def test_none_response_raises_500(self):
        """When the error has no response, status should default to 500."""
        with self.assertRaises(HTTPException) as ctx:
            handle_requests_http_error(self._make_error(status_code=None))
        self.assertEqual(ctx.exception.status_code, 500)


if __name__ == "__main__":
    unittest.main()
