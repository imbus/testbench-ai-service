from unittest.mock import MagicMock

import pytest
import requests

from testbench_ai_service.utils.testbench import get_project_name, get_user_key


class TestGetUserKey:
    """Tests for ``get_user_key``."""

    def test_returns_user_key_from_own_user_data_response(self):
        conn = MagicMock()
        conn.server_url = "https://tb/api/"
        conn.session.get.return_value.json.return_value = {"key": "u42"}
        result = get_user_key(conn)
        assert result == "u42"
        conn.session.get.assert_called_once_with("https://tb/api/2/users/self")

    def test_http_error_propagates(self):
        conn = MagicMock()
        conn.server_url = "https://tb/api/"
        conn.session.get.side_effect = requests.exceptions.HTTPError("401 Unauthorized")
        with pytest.raises(requests.exceptions.HTTPError):
            get_user_key(conn)

    def test_connection_error_propagates(self):
        conn = MagicMock()
        conn.server_url = "https://tb/api/"
        conn.session.get.side_effect = requests.exceptions.ConnectionError("timeout")
        with pytest.raises(requests.exceptions.ConnectionError):
            get_user_key(conn)


class TestGetProjectName:
    """Tests for ``get_project_name``."""

    def test_returns_name_from_project_dict(self):
        conn = MagicMock()
        conn.get_project.return_value = {"name": "Car Configurator"}
        assert get_project_name(conn, "pk1") == "Car Configurator"

    def test_raises_when_get_project_raises(self):
        conn = MagicMock()
        conn.get_project.side_effect = RuntimeError("not found")
        with pytest.raises(RuntimeError):
            get_project_name(conn, "pk_missing")
