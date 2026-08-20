import logging
import logging.config

from testbench_ai_service.models.logging import LoggingConfig, LogLevel

#: Custom level below DEBUG, reserved for request/response payloads. A sink only
#: receives payloads when it is explicitly configured to VERBOSE.
VERBOSE = 5
logging.addLevelName(VERBOSE, LogLevel.VERBOSE.value)


class RequestIdFilter(logging.Filter):
    """Provide a placeholder when a log record is outside an HTTP request."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = "-"
        return True


class ColoredFormatter(logging.Formatter):
    COLOR_MAP = {  # noqa: RUF012
        "VERBOSE": "\033[36m",  # Cyan
        "DEBUG": "\033[35m",  # Magenta
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[41m",  # Red background
    }
    RESET = "\033[0m"

    def format(self, record):
        levelname = record.levelname
        color = self.COLOR_MAP.get(levelname, "")
        colored_levelname = f"{color}{levelname}{self.RESET}"

        record_copy = record.__dict__.copy()
        record_copy["levelname"] = colored_levelname

        updated_record = logging.makeLogRecord(record_copy)
        return super().format(updated_record)


def setup_logging(config: LoggingConfig):
    dict_config = get_log_config_dict(config)
    logging.config.dictConfig(dict_config)


def get_log_config_dict(config: LoggingConfig) -> dict:
    return {
        "version": 1,
        "disable_existing_loggers": True,
        "filters": {
            "request_id": {
                "()": "testbench_ai_service.log.RequestIdFilter",
            }
        },
        "formatters": {
            "console": {
                "()": "testbench_ai_service.log.ColoredFormatter",
                "format": config.console.log_format,
            },
            "file": {"format": config.file.log_format},
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": config.console.log_level.value,
                "formatter": "console",
                "filters": ["request_id"],
                "stream": "ext://sys.stdout",
            },
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": config.file.log_level.value,
                "formatter": "file",
                "filters": ["request_id"],
                "filename": config.file.file_name,
                "mode": "a",
                "maxBytes": 1 * 1024 * 1024,
                "backupCount": 2,
                "encoding": "utf_8",
                "delay": False,
            },
        },
        "loggers": {
            "testbench_ai_service": {
                "handlers": ["console", "file"],
                "level": min(
                    get_log_level_int(config.console.log_level.value),
                    get_log_level_int(config.file.log_level.value),
                ),
                "propagate": False,
            },
            "uvicorn": {
                "handlers": ["console", "file"],
                "level": config.console.log_level.value,
                "propagate": False,
            },
            "uvicorn.access": {
                "handlers": ["console", "file"],
                "level": config.console.log_level.value,
                "propagate": False,
            },
            "uvicorn.error": {
                "handlers": ["console", "file"],
                "level": config.console.log_level.value,
                "propagate": False,
            },
            "uvicorn.asgi": {
                "handlers": ["console", "file"],
                "level": config.console.log_level.value,
                "propagate": False,
            },
            "py.warnings": {
                "handlers": ["console", "file"],
                "level": LogLevel.WARNING.value,
            },
        },
    }


def truncate_payload(payload: str, max_length: int) -> str:
    """Cap *payload* at *max_length* characters. A *max_length* of 0 disables truncation."""
    if max_length and len(payload) > max_length:
        return f"{payload[:max_length]}... (truncated, {len(payload)} characters total)"
    return payload


def get_log_level_int(level_str: str, default: int = logging.INFO) -> int:
    """Resolve a level name to its integer value, including custom levels like VERBOSE."""
    level = logging.getLevelName(level_str.upper())
    if not isinstance(level, int):
        return default
    return int(level)


logging.captureWarnings(True)

logger = logging.getLogger("testbench_ai_service")
