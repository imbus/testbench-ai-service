import unittest

from testbench_ai_service.models.logging import (
    ConsoleLoggerConfig,
    FileLoggerConfig,
    LoggingConfig,
    LogLevel,
)


class TestLogLevel(unittest.TestCase):
    """Tests for the ``LogLevel`` enum."""

    def test_debug_value(self):
        self.assertEqual(LogLevel.DEBUG, "DEBUG")

    def test_info_value(self):
        self.assertEqual(LogLevel.INFO, "INFO")

    def test_warning_value(self):
        self.assertEqual(LogLevel.WARNING, "WARNING")

    def test_error_value(self):
        self.assertEqual(LogLevel.ERROR, "ERROR")


class TestConsoleLoggerConfig(unittest.TestCase):
    """Tests for ``ConsoleLoggerConfig``."""

    def test_default_instance_is_valid(self):
        config = ConsoleLoggerConfig()
        self.assertIsNotNone(config)

    def test_log_level_can_be_set(self):
        config = ConsoleLoggerConfig(log_level=LogLevel.DEBUG)
        self.assertEqual(config.log_level, LogLevel.DEBUG)

    def test_default_log_level_is_info(self):
        self.assertEqual(ConsoleLoggerConfig().log_level, LogLevel.INFO)


class TestFileLoggerConfig(unittest.TestCase):
    """Tests for ``FileLoggerConfig``."""

    def test_default_instance_is_valid(self):
        config = FileLoggerConfig()
        self.assertIsNotNone(config)

    def test_log_level_can_be_set(self):
        config = FileLoggerConfig(log_level=LogLevel.ERROR)
        self.assertEqual(config.log_level, LogLevel.ERROR)


class TestLoggingConfig(unittest.TestCase):
    """Tests for ``LoggingConfig``."""

    def test_default_instance_is_valid(self):
        config = LoggingConfig()
        self.assertIsNotNone(config)

    def test_composes_console_and_file_configs(self):
        config = LoggingConfig(
            console=ConsoleLoggerConfig(log_level=LogLevel.INFO),
            file=FileLoggerConfig(log_level=LogLevel.WARNING),
        )
        self.assertEqual(config.console.log_level, LogLevel.INFO)
        self.assertEqual(config.file.log_level, LogLevel.WARNING)


if __name__ == "__main__":
    unittest.main()
