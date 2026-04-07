import unittest
from unittest.mock import MagicMock

from testbench_ai_service.utils.testbench import get_project_name, get_user_key


class TestGetUserKey(unittest.TestCase):
    """Tests for ``get_user_key``."""

    def test_returns_user_key_from_session_response(self):
        conn = MagicMock()
        conn.server_url = "https://tb/api/"
        conn.session.get.return_value.json.return_value = {"userKey": "u42"}
        result = get_user_key(conn)
        self.assertEqual(result, "u42")
        conn.session.get.assert_called_once_with("https://tb/api/2/login/session")


class TestGetProjectName(unittest.TestCase):
    """Tests for ``get_project_name``."""

    def test_returns_name_from_project_dict(self):
        conn = MagicMock()
        conn.get_project.return_value = {"name": "Car Configurator"}
        self.assertEqual(get_project_name(conn, "pk1"), "Car Configurator")

    def test_raises_when_get_project_raises(self):
        conn = MagicMock()
        conn.get_project.side_effect = RuntimeError("not found")
        with self.assertRaises(RuntimeError):
            get_project_name(conn, "pk_missing")


if __name__ == "__main__":
    unittest.main()
