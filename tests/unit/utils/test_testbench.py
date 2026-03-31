import unittest
from unittest.mock import MagicMock

from testbench_ai_service.utils.testbench import get_cycle_key, get_project_name, get_user_key


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

    def test_returns_none_when_exception_raised(self):
        conn = MagicMock()
        conn.get_project.side_effect = RuntimeError("not found")
        self.assertIsNone(get_project_name(conn, "pk_missing"))


class TestGetCycleKey(unittest.TestCase):
    """Tests for ``get_cycle_key``."""

    def test_returns_none_when_cycle_name_is_empty(self):
        conn = MagicMock()
        self.assertIsNone(get_cycle_key(conn, "pk", "tv", ""))

    def test_returns_none_when_cycle_name_is_none(self):
        conn = MagicMock()
        self.assertIsNone(get_cycle_key(conn, "pk", "tv", None))

    def test_delegates_to_connection_when_cycle_name_given(self):
        conn = MagicMock()
        conn.get_cycle_key_new_play.return_value = "ck99"
        result = get_cycle_key(conn, "pk", "tv", "Sprint 1")
        self.assertEqual(result, "ck99")
        conn.get_cycle_key_new_play.assert_called_once_with("pk", "tv", "Sprint 1")


if __name__ == "__main__":
    unittest.main()
