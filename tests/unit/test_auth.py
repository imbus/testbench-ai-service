import unittest
from unittest.mock import MagicMock, patch
from unittest.mock import patch as _patch

import requests
from fastapi import HTTPException

from testbench_ai_service.auth import validate_session_token
from testbench_ai_service.config import AppConfig


class TestValidateSessionToken(unittest.TestCase):
    """Tests for ``validate_session_token``."""

    def _make_request(self, config):
        mock_request = MagicMock()
        mock_request.app.state.config = config
        return mock_request

    def test_missing_token_raises_401(self):
        with self.assertRaises(HTTPException) as ctx:
            validate_session_token(MagicMock(), session_token=None)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_empty_string_token_raises_401(self):
        with self.assertRaises(HTTPException) as ctx:
            validate_session_token(MagicMock(), session_token="")
        self.assertEqual(ctx.exception.status_code, 401)

    def _make_app_config(self):
        """Create an AppConfig with the URL validator bypassed."""
        with _patch("testbench_ai_service.config.validate_tb_server_url"):
            return AppConfig(tb_server_url="https://tb/api/")

    @patch("testbench_ai_service.auth.TBConnection")
    def test_invalid_token_raises_401(self, mock_tb_conn_class):
        mock_conn = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_conn.check_is_working.side_effect = requests.exceptions.HTTPError(
            "Unauthorized", response=mock_response
        )
        mock_tb_conn_class.return_value = mock_conn

        request = self._make_request(self._make_app_config())
        with self.assertRaises(HTTPException) as ctx:
            validate_session_token(request, session_token="bad-token")
        self.assertEqual(ctx.exception.status_code, 401)

    @patch("testbench_ai_service.auth.TBConnection")
    def test_connection_error_raises_502(self, mock_tb_conn_class):
        mock_conn = MagicMock()
        mock_conn.check_is_working.side_effect = requests.exceptions.ConnectionError("timeout")
        mock_tb_conn_class.return_value = mock_conn

        request = self._make_request(self._make_app_config())
        with self.assertRaises(HTTPException) as ctx:
            validate_session_token(request, session_token="any-token")
        self.assertEqual(ctx.exception.status_code, 502)

    @patch("testbench_ai_service.auth.TBConnection")
    def test_valid_token_is_returned(self, mock_tb_conn_class):
        mock_conn = MagicMock()
        mock_conn.check_is_working.return_value = None
        mock_tb_conn_class.return_value = mock_conn

        request = self._make_request(self._make_app_config())
        result = validate_session_token(request, session_token="valid-token")
        self.assertEqual(result, "valid-token")


if __name__ == "__main__":
    unittest.main()
