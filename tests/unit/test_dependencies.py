import contextlib
import unittest
from unittest.mock import MagicMock, patch

import requests
from fastapi import HTTPException

from testbench_ai_service.auth import AuthInfo, AuthType
from testbench_ai_service.dependencies import get_app_config, get_llm_factory, get_tb_connection


def _make_auth_info(token: str = "test-token") -> AuthInfo:
    return AuthInfo(auth_type=AuthType.SESSION_TOKEN, token=token, user_key="user1")


class TestGetAppConfig(unittest.TestCase):
    def test_returns_config_from_app_state(self):
        mock_config = MagicMock()
        request = MagicMock()
        request.app.state.config = mock_config

        result = get_app_config(request)

        self.assertIs(result, mock_config)


class TestGetLlmFactory(unittest.TestCase):
    def test_returns_llm_factory_from_app_state(self):
        mock_factory = MagicMock()
        request = MagicMock()
        request.app.state.llm_factory = mock_factory

        result = get_llm_factory(request)

        self.assertIs(result, mock_factory)


class TestGetTbConnection(unittest.TestCase):
    def _make_config(self, url="https://tb.example.com/api/"):
        config = MagicMock()
        config.tb_server_url = url
        return config

    def test_yields_connection_with_token_from_auth_info(self):
        config = self._make_config()
        mock_conn = MagicMock()
        auth_info = _make_auth_info("my-token")

        with patch(
            "testbench_ai_service.dependencies.TBConnection", return_value=mock_conn
        ) as mock_cls:
            gen = get_tb_connection(config=config, auth_info=auth_info)
            conn = next(gen)

        self.assertIs(conn, mock_conn)
        # Connection must be created with the token from AuthInfo
        mock_cls.assert_called_once_with(
            server_url=config.tb_server_url, verify=False, sessionToken="my-token"
        )

    def test_raises_502_when_connection_instantiation_fails(self):
        config = self._make_config()
        auth_info = _make_auth_info()

        with patch(
            "testbench_ai_service.dependencies.TBConnection",
            side_effect=requests.exceptions.RequestException("unreachable"),
        ):
            gen = get_tb_connection(config=config, auth_info=auth_info)
            with self.assertRaises(HTTPException) as ctx:
                next(gen)

        self.assertEqual(ctx.exception.status_code, 502)

    def test_closes_connection_after_yield(self):
        config = self._make_config()
        mock_conn = MagicMock()
        auth_info = _make_auth_info()

        with patch("testbench_ai_service.dependencies.TBConnection", return_value=mock_conn):
            gen = get_tb_connection(config=config, auth_info=auth_info)
            next(gen)
            with contextlib.suppress(StopIteration):
                next(gen)

        mock_conn.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
