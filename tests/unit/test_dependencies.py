from unittest.mock import MagicMock

from testbench_ai_service.auth import AuthInfo, AuthType
from testbench_ai_service.dependencies import get_app_config, get_llm_factory, get_tb_connection


def _make_auth_info(token: str = "test-token", conn=None) -> AuthInfo:
    return AuthInfo(
        auth_type=AuthType.SESSION_TOKEN,
        token=token,
        user_key="user1",
        conn=conn if conn is not None else MagicMock(),
    )


class TestGetAppConfig:
    def test_returns_config_from_app_state(self):
        mock_config = MagicMock()
        request = MagicMock()
        request.app.state.config = mock_config

        result = get_app_config(request)

        assert result is mock_config


class TestGetLlmFactory:
    def test_returns_llm_factory_from_app_state(self):
        mock_factory = MagicMock()
        request = MagicMock()
        request.app.state.llm_factory = mock_factory

        result = get_llm_factory(request)

        assert result is mock_factory


class TestGetTbConnection:
    def test_returns_connection_from_auth_info(self):
        mock_conn = MagicMock()
        auth_info = _make_auth_info(conn=mock_conn)

        result = get_tb_connection(auth_info=auth_info)

        assert result is mock_conn
