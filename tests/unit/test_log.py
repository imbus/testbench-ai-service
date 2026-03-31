import logging
import unittest
from io import StringIO
from unittest.mock import patch

from testbench_ai_service.log import (
    ColoredFormatter,
    get_log_config_dict,
    get_log_level_int,
    setup_logging,
)
from testbench_ai_service.models.logging import (
    ConsoleLoggerConfig,
    FileLoggerConfig,
    LoggingConfig,
    LogLevel,
)


class TestColoredFormatter(unittest.TestCase):
    """ColoredFormatter wraps the level-name in ANSI escape codes."""

    def setUp(self):
        self.stream = StringIO()
        self.handler = logging.StreamHandler(self.stream)
        self.formatter = ColoredFormatter("%(levelname)s: %(message)s")
        self.handler.setFormatter(self.formatter)
        self.logger = logging.getLogger("test_colored_formatter")
        self.logger.setLevel(logging.DEBUG)
        self.logger.propagate = False
        self.logger.addHandler(self.handler)

    def tearDown(self):
        self.logger.removeHandler(self.handler)
        self.handler.close()

    def _get_output(self, log_func, msg: str) -> str:
        log_func(msg)
        self.handler.flush()
        return self.stream.getvalue().strip()

    def test_debug_uses_magenta(self):
        output = self._get_output(self.logger.debug, "debug message")
        self.assertIn("\033[35mDEBUG\033[0m", output)
        self.assertTrue(output.endswith("debug message"))

    def test_info_uses_green(self):
        output = self._get_output(self.logger.info, "info message")
        self.assertIn("\033[32mINFO\033[0m", output)

    def test_warning_uses_yellow(self):
        output = self._get_output(self.logger.warning, "warning message")
        self.assertIn("\033[33mWARNING\033[0m", output)

    def test_error_uses_red(self):
        output = self._get_output(self.logger.error, "error message")
        self.assertIn("\033[31mERROR\033[0m", output)

    def test_critical_uses_red_background(self):
        output = self._get_output(self.logger.critical, "critical message")
        self.assertIn("\033[41mCRITICAL\033[0m", output)

    def test_message_text_is_never_coloured(self):
        """Colour escape codes must only wrap the level name, never the message."""
        output = self._get_output(self.logger.info, "original message")
        self.assertTrue(output.endswith("original message"))


class TestGetLogLevelInt(unittest.TestCase):
    """get_log_level_int converts string level names to logging integer constants."""

    def test_debug_returns_correct_int(self):
        self.assertEqual(get_log_level_int("DEBUG"), logging.DEBUG)

    def test_info_returns_correct_int(self):
        self.assertEqual(get_log_level_int("INFO"), logging.INFO)

    def test_lookup_is_case_insensitive(self):
        self.assertEqual(get_log_level_int("debug"), logging.DEBUG)
        self.assertEqual(get_log_level_int("Info"), logging.INFO)

    def test_invalid_level_returns_supplied_default(self):
        self.assertEqual(get_log_level_int("INVALID", default=logging.WARNING), logging.WARNING)


class TestGetLogConfigDict(unittest.TestCase):
    """get_log_config_dict produces a valid logging.config.dictConfig-compatible dict."""

    def setUp(self):
        self.config = LoggingConfig(
            console=ConsoleLoggerConfig(
                log_level=LogLevel.DEBUG,
                log_format="%(levelname)s: %(message)s",
            ),
            file=FileLoggerConfig(
                log_level=LogLevel.INFO,
                log_format="%(asctime)s - %(message)s",
                file_name="app.log",
            ),
        )
        self.result = get_log_config_dict(self.config)

    def test_required_top_level_keys_are_present(self):
        for key in ("version", "disable_existing_loggers", "formatters", "handlers", "loggers"):
            self.assertIn(key, self.result)

    def test_console_formatter_uses_colored_formatter_class(self):
        console_fmt = self.result["formatters"]["console"]
        self.assertEqual(console_fmt["()"], "testbench_ai_service.log.ColoredFormatter")
        self.assertEqual(console_fmt["format"], self.config.console.log_format)

    def test_file_handler_is_configured_correctly(self):
        file_handler = self.result["handlers"]["file"]
        self.assertEqual(file_handler["filename"], self.config.file.file_name)
        self.assertEqual(file_handler["encoding"], "utf_8")
        self.assertEqual(file_handler["maxBytes"], 1 * 1024 * 1024)
        self.assertEqual(file_handler["backupCount"], 2)

    def test_root_logger_level_is_minimum_of_console_and_file(self):
        tb_logger = self.result["loggers"]["testbench_ai_service"]
        # min(DEBUG=10, INFO=20) == DEBUG == 10
        self.assertEqual(tb_logger["level"], logging.DEBUG)


class TestSetupLogging(unittest.TestCase):
    """setup_logging wires logging.config.dictConfig with the produced config dict."""

    @patch("logging.config.dictConfig")
    @patch("testbench_ai_service.log.get_log_config_dict")
    def test_delegates_to_dict_config(self, mock_get_dict, mock_dict_config):
        fake_config = {"version": 1}
        mock_get_dict.return_value = fake_config

        config = LoggingConfig(
            console=ConsoleLoggerConfig(log_level=LogLevel.INFO),
            file=FileLoggerConfig(log_level=LogLevel.ERROR, file_name="out.log"),
        )
        setup_logging(config)

        mock_get_dict.assert_called_once_with(config)
        mock_dict_config.assert_called_once_with(fake_config)


if __name__ == "__main__":
    unittest.main()
