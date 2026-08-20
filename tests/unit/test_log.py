import logging
import logging.config
from io import StringIO
from unittest.mock import patch

import pytest

from testbench_ai_service.log import (
    VERBOSE,
    ColoredFormatter,
    RequestIdFilter,
    get_log_config_dict,
    get_log_level_int,
    setup_logging,
    truncate_payload,
)
from testbench_ai_service.models.logging import (
    ConsoleLoggerConfig,
    FileLoggerConfig,
    LoggingConfig,
    LogLevel,
)


class TestColoredFormatter:
    """ColoredFormatter wraps the level-name in ANSI escape codes."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.stream = StringIO()
        self.handler = logging.StreamHandler(self.stream)
        self.formatter = ColoredFormatter("%(levelname)s: %(message)s")
        self.handler.setFormatter(self.formatter)
        self.logger = logging.getLogger("test_colored_formatter")
        self.logger.setLevel(VERBOSE)
        self.logger.propagate = False
        self.logger.addHandler(self.handler)
        yield
        self.logger.removeHandler(self.handler)
        self.handler.close()

    def _get_output(self, log_func, msg: str) -> str:
        log_func(msg)
        self.handler.flush()
        return str(self.stream.getvalue().strip())

    def test_debug_uses_magenta(self):
        output = self._get_output(self.logger.debug, "debug message")
        assert "\033[35mDEBUG\033[0m" in output
        assert output.endswith("debug message")

    def test_info_uses_green(self):
        output = self._get_output(self.logger.info, "info message")
        assert "\033[32mINFO\033[0m" in output

    def test_warning_uses_yellow(self):
        output = self._get_output(self.logger.warning, "warning message")
        assert "\033[33mWARNING\033[0m" in output

    def test_error_uses_red(self):
        output = self._get_output(self.logger.error, "error message")
        assert "\033[31mERROR\033[0m" in output

    def test_critical_uses_red_background(self):
        output = self._get_output(self.logger.critical, "critical message")
        assert "\033[41mCRITICAL\033[0m" in output

    def test_verbose_uses_cyan(self):
        output = self._get_output(lambda m: self.logger.log(VERBOSE, m), "verbose message")
        assert "\033[36mVERBOSE\033[0m" in output

    def test_message_text_is_never_coloured(self):
        """Colour escape codes must only wrap the level name, never the message."""
        output = self._get_output(self.logger.info, "original message")
        assert output.endswith("original message")


class TestRequestIdFilter:
    def test_uses_placeholder_when_request_id_is_missing(self):
        record = logging.LogRecord("test", logging.INFO, "", 0, "message", (), None)

        assert RequestIdFilter().filter(record) is True
        assert record.request_id == "-"

    def test_preserves_existing_request_id(self):
        record = logging.LogRecord("test", logging.INFO, "", 0, "message", (), None)
        record.request_id = "request-123"

        assert RequestIdFilter().filter(record) is True
        assert record.request_id == "request-123"


class TestGetLogLevelInt:
    """get_log_level_int converts string level names to logging integer constants."""

    def test_debug_returns_correct_int(self):
        assert get_log_level_int("DEBUG") == logging.DEBUG

    def test_info_returns_correct_int(self):
        assert get_log_level_int("INFO") == logging.INFO

    def test_lookup_is_case_insensitive(self):
        assert get_log_level_int("debug") == logging.DEBUG
        assert get_log_level_int("Info") == logging.INFO

    def test_invalid_level_returns_supplied_default(self):
        assert get_log_level_int("INVALID", default=logging.WARNING) == logging.WARNING


class TestGetLogConfigDict:
    """get_log_config_dict produces a valid logging.config.dictConfig-compatible dict."""

    @pytest.fixture(autouse=True)
    def setup(self):
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
        for key in (
            "version",
            "disable_existing_loggers",
            "filters",
            "formatters",
            "handlers",
            "loggers",
        ):
            assert key in self.result

    def test_console_formatter_uses_colored_formatter_class(self):
        console_fmt = self.result["formatters"]["console"]
        assert console_fmt["()"] == "testbench_ai_service.log.ColoredFormatter"
        assert console_fmt["format"] == self.config.console.log_format

    def test_file_handler_is_configured_correctly(self):
        file_handler = self.result["handlers"]["file"]
        assert file_handler["filters"] == ["request_id"]
        assert file_handler["filename"] == self.config.file.file_name
        assert file_handler["encoding"] == "utf_8"
        assert file_handler["maxBytes"] == 1 * 1024 * 1024
        assert file_handler["backupCount"] == 2

    def test_root_logger_level_is_minimum_of_console_and_file(self):
        tb_logger = self.result["loggers"]["testbench_ai_service"]
        # min(DEBUG=10, INFO=20) == DEBUG == 10
        assert tb_logger["level"] == logging.DEBUG


class TestSetupLogging:
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


class TestVerboseLevel:
    """VERBOSE is a custom level below DEBUG, used for request/response payloads."""

    def test_verbose_is_below_debug(self):
        assert VERBOSE < logging.DEBUG

    def test_verbose_level_name_is_registered(self):
        assert logging.getLevelName(VERBOSE) == "VERBOSE"

    def test_get_log_level_int_resolves_verbose(self):
        assert get_log_level_int("VERBOSE") == VERBOSE

    def test_get_log_level_int_resolves_verbose_case_insensitively(self):
        assert get_log_level_int("verbose") == VERBOSE

    def test_log_level_enum_exposes_verbose(self):
        assert LogLevel.VERBOSE.value == "VERBOSE"

    def test_logger_level_is_verbose_when_a_single_sink_requests_it(self):
        """A file sink at VERBOSE must pull the logger level down, or payloads never emit."""
        config = LoggingConfig(
            console=ConsoleLoggerConfig(log_level=LogLevel.INFO),
            file=FileLoggerConfig(log_level=LogLevel.VERBOSE, file_name="app.log"),
        )
        result = get_log_config_dict(config)
        assert result["loggers"]["testbench_ai_service"]["level"] == VERBOSE

    def test_dict_config_accepts_verbose_as_handler_level(self):
        """dictConfig must resolve the "VERBOSE" string, including for uvicorn's copy."""
        config = LoggingConfig(
            console=ConsoleLoggerConfig(log_level=LogLevel.VERBOSE),
            file=FileLoggerConfig(log_level=LogLevel.VERBOSE, file_name=self.log_file),
        )
        logging.config.dictConfig(get_log_config_dict(config))
        assert logging.getLogger("testbench_ai_service").isEnabledFor(VERBOSE)

    @pytest.fixture(autouse=True)
    def log_file(self, tmp_path):
        self.log_file = str(tmp_path / "verbose.log")
        yield
        # Detach the handlers dictConfig attached, so later tests start clean.
        tb_logger = logging.getLogger("testbench_ai_service")
        for handler in list(tb_logger.handlers):
            tb_logger.removeHandler(handler)
            handler.close()
        tb_logger.setLevel(logging.NOTSET)
        tb_logger.propagate = True


class TestMaxPayloadLength:
    """Payload truncation is configurable on the logging config."""

    def test_defaults_to_4000(self):
        assert LoggingConfig().max_payload_length == 4000


class TestTruncatePayload:
    """truncate_payload caps a payload and states how long the original was."""

    def test_short_payload_is_returned_unchanged(self):
        assert truncate_payload("short", 100) == "short"

    def test_payload_at_the_limit_is_returned_unchanged(self):
        assert truncate_payload("x" * 10, 10) == "x" * 10

    def test_long_payload_is_cut_and_marked(self):
        result = truncate_payload("x" * 50, 10)
        assert result == "xxxxxxxxxx... (truncated, 50 characters total)"

    def test_zero_limit_disables_truncation(self):
        assert truncate_payload("x" * 50, 0) == "x" * 50
