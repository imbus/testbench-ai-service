import logging
import logging.config

from testbench_ai_service.models.logging import LoggingConfig, LogLevel


class ColoredFormatter(logging.Formatter):
    COLOR_MAP = {  # noqa: RUF012
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
                "stream": "ext://sys.stdout",
            },
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": config.file.log_level.value,
                "formatter": "file",
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


def get_log_level_int(level_str: str, default: int = logging.INFO) -> int:
    level = getattr(logging, level_str.upper(), default)
    return int(level)


logging.captureWarnings(True)

logger = logging.getLogger("testbench_ai_service")
