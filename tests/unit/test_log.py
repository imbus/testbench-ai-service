import json
import logging
import sys
from io import StringIO
from unittest.mock import patch

import pytest

from testbench_ai_service.log import (
    ActivityRecordFilter,
    ColoredFormatter,
    JsonLineFormatter,
    LogContextFilter,
    RequestIdFilter,
    build_activity_handler,
    get_log_config_dict,
    get_log_level_int,
    log_context,
    setup_logging,
)
from testbench_ai_service.models.logging import (
    ActivityLoggerConfig,
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
        self.logger.setLevel(logging.DEBUG)
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


def _record(msg="m", level=logging.INFO, exc_info=None):
    return logging.LogRecord("testbench_ai_service.x", level, __file__, 1, msg, None, exc_info)


class TestLogContextFilter:
    def test_outside_any_context_is_service(self):
        record = _record()
        assert LogContextFilter().filter(record) is True
        assert record.scope == "service"
        assert record.user_key is None
        assert record.request_id == "-"

    def test_inside_a_request_is_request(self):
        with log_context(in_request=True):
            record = _record()
            LogContextFilter().filter(record)
        assert record.scope == "request"

    def test_user_wins_over_request(self):
        with log_context(in_request=True), log_context(user_key="u-1", run_id="r-1"):
            record = _record()
            LogContextFilter().filter(record)
        assert record.scope == "user"
        assert record.user_key == "u-1"
        assert record.run_id == "r-1"

    def test_values_are_restored_on_exit_also_nested(self):
        with log_context(user_key="outer"):
            with log_context(user_key="inner"):
                pass
            record = _record()
            LogContextFilter().filter(record)
        assert record.user_key == "outer"
        after = _record()
        LogContextFilter().filter(after)
        assert after.user_key is None

    def test_unknown_key_is_rejected(self):
        with pytest.raises(TypeError), log_context(nope="x"):
            pass


class TestActivityRecordFilter:
    @pytest.mark.parametrize(
        ("scope", "passes"),
        [("user", True), ("service", True), ("request", False)],
    )
    def test_scopes(self, scope, passes):
        record = _record()
        record.scope = scope
        assert ActivityRecordFilter().filter(record) is passes

    def test_record_without_scope_is_dropped(self):
        assert ActivityRecordFilter().filter(_record()) is False


class TestJsonLineFormatter:
    def test_one_line_with_all_fields(self):
        with log_context(user_key="u-1", agent="reviewer", project_key="p-1", run_id="r-1"):
            record = _record("hello %s")
            record.args = ("world",)
            LogContextFilter().filter(record)
        out = JsonLineFormatter().format(record)
        assert "\n" not in out
        entry = json.loads(out)
        assert entry["message"] == "hello world"
        assert entry["level"] == "INFO"
        assert entry["source"] == "testbench_ai_service.x"
        assert entry["scope"] == "user"
        assert entry["user_key"] == "u-1"
        assert entry["agent"] == "reviewer"
        assert entry["ts"].endswith("+00:00")
        assert "exc" not in entry

    def test_traceback_stays_in_the_same_entry(self):
        try:
            raise ValueError("boom")
        except ValueError:
            record = _record("failed", logging.ERROR, sys.exc_info())
        LogContextFilter().filter(record)
        out = JsonLineFormatter().format(record)
        assert "\n" not in out
        assert "ValueError: boom" in json.loads(out)["exc"]


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
        assert file_handler["filters"] == ["log_context"]
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


class TestActivityHandler:
    def _emit(self, handler, msg, level=logging.INFO):
        record = _record(msg, level)
        if handler.filter(record):
            handler.emit(record)

    def test_writes_user_and_service_but_never_request(self, tmp_path):
        path = tmp_path / "act.jsonl"
        handler = build_activity_handler(str(path), 1024 * 1024, 1)
        try:
            self._emit(handler, "startup")
            with log_context(in_request=True):
                self._emit(handler, "request body")
                with log_context(user_key="u-1"):
                    self._emit(handler, "agent done")
        finally:
            handler.close()
        entries = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        assert [(e["message"], e["scope"]) for e in entries] == [
            ("startup", "service"),
            ("agent done", "user"),
        ]


@pytest.fixture
def restore_logging():
    """Undo what a real setup_logging does: it replaces handlers and disables loggers."""
    loggers = [logging.root] + [
        lg for lg in logging.root.manager.loggerDict.values() if isinstance(lg, logging.Logger)
    ]
    saved = {lg: (lg.handlers[:], lg.level, lg.propagate, lg.disabled) for lg in loggers}
    yield
    for lg in [logging.root] + [
        lg for lg in logging.root.manager.loggerDict.values() if isinstance(lg, logging.Logger)
    ]:
        handlers, level, propagate, disabled = saved.get(lg, ([], logging.NOTSET, True, False))
        for h in lg.handlers[:]:
            lg.removeHandler(h)
            if h not in handlers:
                h.close()
        for h in handlers:
            lg.addHandler(h)
        lg.setLevel(level)
        lg.propagate = propagate
        lg.disabled = disabled


class TestActivityConfigDict:
    def test_enabled_by_default_and_not_on_access_log(self):
        result = get_log_config_dict(LoggingConfig())
        handler = result["handlers"]["activity"]
        assert handler["()"] == "testbench_ai_service.log.build_activity_handler"
        assert handler["file_name"] == "testbench-ai-service.activity.jsonl"
        assert handler["level"] == "INFO"
        for name in ("testbench_ai_service", "uvicorn", "uvicorn.error"):
            assert "activity" in result["loggers"][name]["handlers"]
        assert "activity" not in result["loggers"]["uvicorn.access"]["handlers"]

    def test_disabled_removes_the_handler(self):
        result = get_log_config_dict(LoggingConfig(activity=ActivityLoggerConfig(enabled=False)))
        assert "activity" not in result["handlers"]
        for logger_cfg in result["loggers"].values():
            assert "activity" not in logger_cfg["handlers"]

    def test_service_logger_level_covers_the_activity_level(self):
        config = LoggingConfig(
            console=ConsoleLoggerConfig(log_level=LogLevel.ERROR),
            file=FileLoggerConfig(log_level=LogLevel.ERROR),
            activity=ActivityLoggerConfig(log_level=LogLevel.INFO),
        )
        result = get_log_config_dict(config)
        assert result["loggers"]["testbench_ai_service"]["level"] == logging.INFO

    def test_uvicorn_service_events_reach_the_activity_sink(self):
        config = LoggingConfig(
            console=ConsoleLoggerConfig(log_level=LogLevel.ERROR),
            file=FileLoggerConfig(log_level=LogLevel.ERROR),
            activity=ActivityLoggerConfig(log_level=LogLevel.INFO),
        )
        loggers = get_log_config_dict(config)["loggers"]
        assert loggers["uvicorn"]["level"] == logging.INFO
        assert loggers["uvicorn.error"]["level"] == logging.INFO
        assert loggers["uvicorn.access"]["level"] == "ERROR"

    def test_uvicorn_levels_without_activity_are_console_and_file_minimum(self):
        config = LoggingConfig(
            console=ConsoleLoggerConfig(log_level=LogLevel.ERROR),
            file=FileLoggerConfig(log_level=LogLevel.ERROR),
            activity=ActivityLoggerConfig(enabled=False),
        )
        loggers = get_log_config_dict(config)["loggers"]
        assert loggers["uvicorn"]["level"] == logging.ERROR
        assert loggers["uvicorn.error"]["level"] == logging.ERROR

    def test_reapplying_keeps_exactly_one_activity_handler(self, tmp_path, restore_logging):
        # Review Focus 5: hot reload calls setup_logging again.
        config = LoggingConfig(
            file=FileLoggerConfig(file_name=str(tmp_path / "svc.log")),
            activity=ActivityLoggerConfig(file_name=str(tmp_path / "act.jsonl")),
        )
        service = logging.getLogger("testbench_ai_service")
        setup_logging(config)
        setup_logging(config)
        files = [h.baseFilename for h in service.handlers if hasattr(h, "baseFilename")]
        assert files.count(str(tmp_path / "act.jsonl")) == 1
        setup_logging(config.model_copy(update={"activity": ActivityLoggerConfig(enabled=False)}))
        assert not any(
            getattr(h, "baseFilename", "").endswith("act.jsonl") for h in service.handlers
        )
