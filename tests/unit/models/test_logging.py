from testbench_ai_service.models.logging import (
    ConsoleLoggerConfig,
    FileLoggerConfig,
    LoggingConfig,
    LogLevel,
)


class TestLogLevel:
    """Tests for the ``LogLevel`` enum."""

    def test_debug_value(self):
        assert LogLevel.DEBUG == "DEBUG"

    def test_info_value(self):
        assert LogLevel.INFO == "INFO"

    def test_warning_value(self):
        assert LogLevel.WARNING == "WARNING"

    def test_error_value(self):
        assert LogLevel.ERROR == "ERROR"


class TestConsoleLoggerConfig:
    """Tests for ``ConsoleLoggerConfig``."""

    def test_default_log_level_is_info(self):
        assert ConsoleLoggerConfig().log_level == LogLevel.INFO

    def test_log_level_can_be_set(self):
        config = ConsoleLoggerConfig(log_level=LogLevel.DEBUG)
        assert config.log_level == LogLevel.DEBUG


class TestFileLoggerConfig:
    """Tests for ``FileLoggerConfig``."""

    def test_default_log_level_is_info(self):
        assert FileLoggerConfig().log_level == LogLevel.INFO

    def test_log_level_can_be_set(self):
        config = FileLoggerConfig(log_level=LogLevel.ERROR)
        assert config.log_level == LogLevel.ERROR


class TestLoggingConfig:
    """Tests for ``LoggingConfig``."""

    def test_default_console_and_file_configs_exist(self):
        config = LoggingConfig()
        assert isinstance(config.console, ConsoleLoggerConfig)
        assert isinstance(config.file, FileLoggerConfig)

    def test_composes_console_and_file_configs(self):
        config = LoggingConfig(
            console=ConsoleLoggerConfig(log_level=LogLevel.INFO),
            file=FileLoggerConfig(log_level=LogLevel.WARNING),
        )
        assert config.console.log_level == LogLevel.INFO
        assert config.file.log_level == LogLevel.WARNING
