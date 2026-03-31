import contextlib
import unittest
from unittest.mock import MagicMock, patch

import requests
from fastapi import HTTPException

from testbench_ai_service.dependencies import get_app_config, get_llm_factory, get_tb_connection


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

    def test_yields_connection_when_server_reachable(self):
        config = self._make_config()
        mock_conn = MagicMock()

        with patch("testbench_ai_service.dependencies.TBConnection", return_value=mock_conn):
            gen = get_tb_connection(config=config, session_token="tok")
            conn = next(gen)
            self.assertIs(conn, mock_conn)
            mock_conn.check_is_working.assert_called_once()

    def test_raises_502_when_server_unreachable(self):
        config = self._make_config()
        mock_conn = MagicMock()
        mock_conn.check_is_working.side_effect = requests.exceptions.ConnectionError("unreachable")

        with patch("testbench_ai_service.dependencies.TBConnection", return_value=mock_conn):
            gen = get_tb_connection(config=config, session_token="tok")
            with self.assertRaises(HTTPException) as ctx:
                next(gen)

        self.assertEqual(ctx.exception.status_code, 502)

    def test_closes_connection_after_yield(self):
        config = self._make_config()
        mock_conn = MagicMock()

        with patch("testbench_ai_service.dependencies.TBConnection", return_value=mock_conn):
            gen = get_tb_connection(config=config, session_token="tok")
            next(gen)
            with contextlib.suppress(StopIteration):
                next(gen)

        mock_conn.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
