import unittest
from unittest.mock import MagicMock, patch
from unittest.mock import patch as _patch

import requests
from fastapi import HTTPException

from testbench_ai_service.auth import AuthInfo, AuthType, _is_jwt, _validate_token, get_auth_info
from testbench_ai_service.config import AppConfig


def _make_app_config() -> AppConfig:
    """Create an AppConfig with the URL validator bypassed."""
    with _patch("testbench_ai_service.config.validate_tb_server_url"):
        return AppConfig(tb_server_url="https://tb/api/")


def _make_request(config: AppConfig) -> MagicMock:
    mock_request = MagicMock()
    mock_request.app.state.config = config
    return mock_request


# A minimal well-formed JWT (header.payload.signature — no signature verification)
_VALID_JWT = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJzdWIiOiJ1c2VyMSIsInNjb3BlIjp7InByb2oiOiJQMSIsInRvdiI6IlQxIn19"
    ".SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
)
_SESSION_TOKEN = "opaque-session-token-no-dots"


class TestIsJwt(unittest.TestCase):
    """Unit tests for the ``_is_jwt`` format detector."""

    def test_valid_jwt_returns_true(self):
        self.assertTrue(_is_jwt(_VALID_JWT))

    def test_opaque_token_returns_false(self):
        self.assertFalse(_is_jwt(_SESSION_TOKEN))

    def test_two_segments_returns_false(self):
        self.assertFalse(_is_jwt("a.b"))

    def test_four_segments_returns_false(self):
        self.assertFalse(_is_jwt("a.b.c.d"))

    def test_three_segments_but_invalid_base64_returns_false(self):
        self.assertFalse(_is_jwt("!!!.!!!.!!!"))


class TestGetAuthInfo(unittest.TestCase):
    """Tests for the ``get_auth_info`` FastAPI dependency."""

    def _call(self, session_token=None, jwt_token=None, config=None):
        """Invoke ``get_auth_info`` directly (bypassing FastAPI DI)."""
        config = config or _make_app_config()
        request = _make_request(config)
        return get_auth_info(request, session_token=session_token, jwt_token=jwt_token)

    # --- missing / empty token ---

    def test_missing_token_raises_401(self):
        with self.assertRaises(HTTPException) as ctx:
            self._call()
        self.assertEqual(ctx.exception.status_code, 401)

    def test_empty_string_raises_401(self):
        with self.assertRaises(HTTPException) as ctx:
            self._call(session_token="")
        self.assertEqual(ctx.exception.status_code, 401)

    # --- session token path ---

    @patch("testbench_ai_service.auth._validate_token", return_value="user-key-1")
    def test_session_token_returns_session_auth_type(self, mock_validate):
        result = self._call(session_token=_SESSION_TOKEN)

        self.assertIsInstance(result, AuthInfo)
        self.assertEqual(result.auth_type, AuthType.SESSION_TOKEN)
        self.assertEqual(result.token, _SESSION_TOKEN)
        self.assertEqual(result.user_key, "user-key-1")
        mock_validate.assert_called_once()

    @patch("testbench_ai_service.auth._validate_token")
    def test_invalid_session_token_raises_401(self, mock_validate):
        mock_validate.side_effect = HTTPException(status_code=401, detail="Invalid")
        with self.assertRaises(HTTPException) as ctx:
            self._call(session_token=_SESSION_TOKEN)
        self.assertEqual(ctx.exception.status_code, 401)

    # --- JWT token path ---

    @patch("testbench_ai_service.auth._validate_token", return_value="jwt-user-key")
    def test_jwt_token_returns_jwt_auth_type(self, mock_validate):
        result = self._call(jwt_token=_VALID_JWT)

        self.assertEqual(result.auth_type, AuthType.JWT_TOKEN)
        self.assertEqual(result.token, _VALID_JWT)
        self.assertEqual(result.user_key, "jwt-user-key")

    # --- server unreachable ---

    @patch("testbench_ai_service.auth._validate_token")
    def test_connection_error_raises_502(self, mock_validate):
        mock_validate.side_effect = HTTPException(status_code=502, detail="Gateway")
        with self.assertRaises(HTTPException) as ctx:
            self._call(session_token=_SESSION_TOKEN)
        self.assertEqual(ctx.exception.status_code, 502)

    # --- _jwt preferred over _session when both present ---

    @patch("testbench_ai_service.auth._validate_token", return_value="u")
    def test_jwt_takes_precedence_over_session_token(self, mock_validate):
        result = self._call(session_token=_SESSION_TOKEN, jwt_token=_VALID_JWT)
        self.assertEqual(result.auth_type, AuthType.JWT_TOKEN)
        self.assertEqual(result.token, _VALID_JWT)


class TestValidateToken(unittest.TestCase):
    """Tests for the ``_validate_token`` helper (integration with TBConnection)."""

    def _make_app_config(self):
        return _make_app_config()

    @patch("testbench_ai_service.auth.TBConnection")
    @patch("testbench_ai_service.auth.get_user_key", return_value="uk1")
    def test_valid_token_returns_user_key(self, mock_get_user_key, mock_conn_cls):
        result = _validate_token("https://tb/api/", "some-token")

        self.assertEqual(result, "uk1")
        mock_conn_cls.assert_called_once()
        mock_get_user_key.assert_called_once()

    @patch("testbench_ai_service.auth.TBConnection")
    @patch(
        "testbench_ai_service.auth.get_user_key",
        side_effect=requests.exceptions.HTTPError("Unauthorized"),
    )
    def test_http_error_raises_401(self, mock_get_user_key, mock_conn_cls):
        with self.assertRaises(HTTPException) as ctx:
            _validate_token("https://tb/api/", "bad-token")
        self.assertEqual(ctx.exception.status_code, 401)

    @patch("testbench_ai_service.auth.TBConnection")
    @patch(
        "testbench_ai_service.auth.get_user_key",
        side_effect=requests.exceptions.ConnectionError("timeout"),
    )
    def test_connection_error_raises_502(self, mock_get_user_key, mock_conn_cls):
        with self.assertRaises(HTTPException) as ctx:
            _validate_token("https://tb/api/", "any-token")
        self.assertEqual(ctx.exception.status_code, 502)

    @patch("testbench_ai_service.auth.TBConnection")
    @patch("testbench_ai_service.auth.get_user_key", return_value="uk1")
    def test_connection_is_always_closed(self, mock_get_user_key, mock_conn_cls):
        mock_conn = MagicMock()
        mock_conn_cls.return_value = mock_conn

        _validate_token("https://tb/api/", "tok")

        mock_conn.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
