from unittest.mock import MagicMock, patch

import pytest
import requests
from fastapi import HTTPException

from testbench_ai_service.auth import (
    AuthInfo,
    AuthType,
    _is_jwt,
    _validate_token,
    validate_auth_token,
)
from testbench_ai_service.config import AppConfig
from testbench_ai_service.transport import ResilientHTTPAdapter


def _make_app_config() -> AppConfig:
    with patch("testbench_ai_service.config.validate_tb_server_url"):
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


class TestIsJwt:
    """Unit tests for the ``_is_jwt`` format detector."""

    def test_valid_jwt_returns_true(self):
        assert _is_jwt(_VALID_JWT)

    def test_opaque_token_returns_false(self):
        assert not _is_jwt(_SESSION_TOKEN)

    def test_two_segments_returns_false(self):
        assert not _is_jwt("a.b")

    def test_four_segments_returns_false(self):
        assert not _is_jwt("a.b.c.d")

    def test_three_segments_but_invalid_base64_returns_false(self):
        assert not _is_jwt("!!!.!!!.!!!")


class TestValidateAuthToken:
    """Tests for the ``validate_auth_token`` FastAPI dependency."""

    def _call(self, session_token=None, jwt_token=None, config=None):
        config = config or _make_app_config()
        request = _make_request(config)
        gen = validate_auth_token(request, session_token=session_token, jwt_token=jwt_token)
        try:
            return next(gen)
        finally:
            gen.close()

    def test_missing_token_raises_401(self):
        with pytest.raises(HTTPException) as exc_info:
            self._call()
        assert exc_info.value.status_code == 401

    def test_empty_string_raises_401(self):
        with pytest.raises(HTTPException) as exc_info:
            self._call(session_token="")
        assert exc_info.value.status_code == 401

    @patch("testbench_ai_service.auth._validate_token", return_value=("user-key-1", MagicMock()))
    def test_session_token_returns_session_auth_type(self, mock_validate):
        result = self._call(session_token=_SESSION_TOKEN)

        assert isinstance(result, AuthInfo)
        assert result.auth_type == AuthType.SESSION_TOKEN
        assert result.token == _SESSION_TOKEN
        assert result.user_key == "user-key-1"
        mock_validate.assert_called_once()

    @patch("testbench_ai_service.auth._validate_token")
    def test_invalid_session_token_raises_401(self, mock_validate):
        mock_validate.side_effect = HTTPException(status_code=401, detail="Invalid")
        with pytest.raises(HTTPException) as exc_info:
            self._call(session_token=_SESSION_TOKEN)
        assert exc_info.value.status_code == 401

    @patch("testbench_ai_service.auth._validate_token", return_value=("jwt-user-key", MagicMock()))
    def test_jwt_token_returns_jwt_auth_type(self, mock_validate):
        result = self._call(jwt_token=_VALID_JWT)

        assert result.auth_type == AuthType.JWT_TOKEN
        assert result.token == _VALID_JWT
        assert result.user_key == "jwt-user-key"

    @patch("testbench_ai_service.auth._validate_token")
    def test_connection_error_raises_502(self, mock_validate):
        mock_validate.side_effect = HTTPException(status_code=502, detail="Gateway")
        with pytest.raises(HTTPException) as exc_info:
            self._call(session_token=_SESSION_TOKEN)
        assert exc_info.value.status_code == 502

    @patch("testbench_ai_service.auth._validate_token", return_value=("u", MagicMock()))
    def test_jwt_takes_precedence_over_session_token(self, mock_validate):
        result = self._call(session_token=_SESSION_TOKEN, jwt_token=_VALID_JWT)
        assert result.auth_type == AuthType.JWT_TOKEN
        assert result.token == _VALID_JWT


class TestValidateToken:
    """Tests for the ``_validate_token`` helper (integration with TBConnection)."""

    @patch("testbench_ai_service.auth.TBConnection")
    @patch("testbench_ai_service.auth.get_user_key", return_value="uk1")
    def test_valid_token_returns_user_key(self, mock_get_user_key, mock_conn_cls):
        user_key, _ = _validate_token("https://tb/api/", "some-token", True)

        assert user_key == "uk1"
        mock_conn_cls.assert_called_once()
        mock_get_user_key.assert_called_once()

    @patch("testbench_ai_service.auth.TBConnection")
    @patch(
        "testbench_ai_service.auth.get_user_key",
        side_effect=requests.exceptions.HTTPError("Unauthorized"),
    )
    def test_http_error_raises_401(self, mock_get_user_key, mock_conn_cls):
        with pytest.raises(HTTPException) as exc_info:
            _validate_token("https://tb/api/", "bad-token", True)
        assert exc_info.value.status_code == 401

    @patch("testbench_ai_service.auth.TBConnection")
    @patch(
        "testbench_ai_service.auth.get_user_key",
        side_effect=requests.exceptions.ConnectionError("timeout"),
    )
    def test_connection_error_raises_502(self, mock_get_user_key, mock_conn_cls):
        with pytest.raises(HTTPException) as exc_info:
            _validate_token("https://tb/api/", "any-token", True)
        assert exc_info.value.status_code == 502

    @patch("testbench_ai_service.auth.TBConnection")
    @patch("testbench_ai_service.auth.get_user_key", return_value="uk1")
    def test_session_is_hardened_with_timeouts_and_retries(self, mock_get_user_key, mock_conn_cls):
        """The connection's session must get bounded timeouts and retries."""
        mock_conn = MagicMock()
        mock_conn.session = requests.Session()
        mock_conn_cls.return_value = mock_conn

        _validate_token(
            "https://tb/api/",
            "tok",
            True,
            connect_timeout=4.0,
            read_timeout=8.0,
            max_retries=2,
        )

        adapter = mock_conn.session.get_adapter("https://tb/api/")
        assert isinstance(adapter, ResilientHTTPAdapter)
        assert adapter.timeout == (4.0, 8.0)
        assert adapter.max_retries.total == 2

    @patch("testbench_ai_service.auth.TBConnection")
    @patch("testbench_ai_service.auth.get_user_key", return_value="uk1")
    def test_bootstrap_is_bounded_by_a_connection_timeout(self, mock_get_user_key, mock_conn_cls):
        """The library mounts its own adapter partway through ``Connection.session``.

        That adapter's timeout is ``None`` unless ``connection_timeout_sec`` is passed to
        the constructor, so the bootstrap requests that run before ``harden_connection``
        can take effect would otherwise wait forever.
        """
        mock_conn = MagicMock()
        mock_conn.session = requests.Session()
        mock_conn_cls.return_value = mock_conn

        _validate_token("https://tb/api/", "tok", True, connect_timeout=4.0, read_timeout=8.0)

        assert mock_conn_cls.call_args.kwargs["connection_timeout_sec"] == 8

    @patch("testbench_ai_service.auth.TBConnection")
    @patch("testbench_ai_service.auth.get_user_key", return_value="uk1")
    def test_bootstrap_timeout_is_never_rounded_down_to_zero(
        self, mock_get_user_key, mock_conn_cls
    ):
        """``connection_timeout_sec`` is an int; a sub-second read timeout must not
        become ``0``, which requests would treat as an immediate timeout."""
        mock_conn = MagicMock()
        mock_conn.session = requests.Session()
        mock_conn_cls.return_value = mock_conn

        _validate_token("https://tb/api/", "tok", True, read_timeout=0.5)

        assert mock_conn_cls.call_args.kwargs["connection_timeout_sec"] == 1

    @patch("testbench_ai_service.auth.TBConnection")
    @patch("testbench_ai_service.auth.get_user_key", return_value="uk1")
    def test_connection_not_closed_on_success(self, mock_get_user_key, mock_conn_cls):
        mock_conn = MagicMock()
        mock_conn_cls.return_value = mock_conn

        _validate_token("https://tb/api/", "tok", True)

        mock_conn.close.assert_not_called()

    @patch("testbench_ai_service.auth.TBConnection")
    @patch(
        "testbench_ai_service.auth.get_user_key",
        side_effect=requests.exceptions.HTTPError("Unauthorized"),
    )
    def test_connection_closed_on_http_error(self, mock_get_user_key, mock_conn_cls):
        mock_conn = MagicMock()
        mock_conn_cls.return_value = mock_conn

        with pytest.raises(HTTPException):
            _validate_token("https://tb/api/", "bad-token", True)

        mock_conn.close.assert_called_once()

    @patch("testbench_ai_service.auth.TBConnection")
    @patch(
        "testbench_ai_service.auth.get_user_key",
        side_effect=requests.exceptions.ConnectionError("timeout"),
    )
    def test_connection_closed_on_connection_error(self, mock_get_user_key, mock_conn_cls):
        mock_conn = MagicMock()
        mock_conn_cls.return_value = mock_conn

        with pytest.raises(HTTPException):
            _validate_token("https://tb/api/", "any-token", True)

        mock_conn.close.assert_called_once()

    @patch("testbench_ai_service.auth.TBConnection")
    @patch("testbench_ai_service.auth.get_user_key", return_value="uk1")
    def test_verify_bool_passed_to_tbconnection(self, mock_get_user_key, mock_conn_cls):
        _validate_token("https://tb/api/", "tok", False)
        mock_conn_cls.assert_called_once()
        assert mock_conn_cls.call_args.args == ("https://tb/api/",)
        assert mock_conn_cls.call_args.kwargs["verify"] is False
        assert mock_conn_cls.call_args.kwargs["sessionToken"] == "tok"

    @patch("testbench_ai_service.auth.TBConnection")
    @patch("testbench_ai_service.auth.get_user_key", return_value="uk1")
    def test_verify_ca_bundle_path_passed_to_tbconnection(self, mock_get_user_key, mock_conn_cls):
        _validate_token("https://tb/api/", "tok", "/path/to/ca.pem")
        mock_conn_cls.assert_called_once()
        assert mock_conn_cls.call_args.args == ("https://tb/api/",)
        assert mock_conn_cls.call_args.kwargs["verify"] == "/path/to/ca.pem"
        assert mock_conn_cls.call_args.kwargs["sessionToken"] == "tok"
