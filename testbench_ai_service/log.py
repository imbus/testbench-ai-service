import json
import logging
import logging.config
import logging.handlers
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone

from testbench_ai_service.models.logging import LoggingConfig, LogLevel

log_user_key: ContextVar[str | None] = ContextVar("log_user_key", default=None)
log_username: ContextVar[str | None] = ContextVar("log_username", default=None)
log_project_key: ContextVar[str | None] = ContextVar("log_project_key", default=None)
log_run_id: ContextVar[str | None] = ContextVar("log_run_id", default=None)
log_agent: ContextVar[str | None] = ContextVar("log_agent", default=None)
log_in_request: ContextVar[bool] = ContextVar("log_in_request", default=False)

_CONTEXT_VARS: dict[str, ContextVar] = {
    "user_key": log_user_key,
    "username": log_username,
    "project_key": log_project_key,
    "run_id": log_run_id,
    "agent": log_agent,
    "in_request": log_in_request,
}

_RECORD_FIELDS = ("user_key", "username", "project_key", "run_id", "agent")


@contextmanager
def log_context(**values: str | bool | None) -> Iterator[None]:
    """Mark every record logged inside the block; restores the outer values on exit."""
    unknown = set(values) - _CONTEXT_VARS.keys()
    if unknown:
        raise TypeError(f"Unknown log context field(s): {sorted(unknown)}")
    tokens = [
        (_CONTEXT_VARS[name], _CONTEXT_VARS[name].set(value)) for name, value in values.items()
    ]
    try:
        yield
    finally:
        for var, token in reversed(tokens):
            var.reset(token)


class LogContextFilter(logging.Filter):
    """Copy the log context onto the record and classify its scope (design D4).

    ``user`` -- logged on behalf of a user; ``request`` -- inside an HTTP request
    but tied to no user; ``service`` -- neither.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = "-"
        for name in _RECORD_FIELDS:
            setattr(record, name, _CONTEXT_VARS[name].get())
        if record.user_key is not None:
            record.scope = "user"
        elif log_in_request.get():
            record.scope = "request"
        else:
            record.scope = "service"
        return True


# Kept so existing imports keep working; the filter now does more than request ids.
RequestIdFilter = LogContextFilter


class ActivityRecordFilter(logging.Filter):
    """Only user and service records reach the activity sink (design D4/D5).

    A record without a scope -- LogContextFilter did not run -- counts as
    ``request`` and is dropped: fail closed.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        return getattr(record, "scope", "request") in ("user", "service")


class JsonLineFormatter(logging.Formatter):
    """One JSON object per record and line; a traceback stays inside its record."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, str | None] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname,
            "source": record.name,
            "message": record.getMessage(),
            "scope": getattr(record, "scope", "request"),
        }
        for name in _RECORD_FIELDS:
            entry[name] = getattr(record, name, None)
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        elif record.exc_text:
            entry["exc"] = record.exc_text
        return json.dumps(entry, ensure_ascii=False)


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


def build_activity_handler(file_name: str, max_bytes: int, backup_count: int) -> logging.Handler:
    """The activity sink, filters and formatter attached (dictConfig factory)."""
    handler = logging.handlers.RotatingFileHandler(
        file_name, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
    )
    # Order matters: the scope is set by LogContextFilter and read by ActivityRecordFilter.
    handler.addFilter(LogContextFilter())
    handler.addFilter(ActivityRecordFilter())
    handler.setFormatter(JsonLineFormatter())
    return handler


def setup_logging(config: LoggingConfig):
    dict_config = get_log_config_dict(config)
    logging.config.dictConfig(dict_config)


def get_log_config_dict(config: LoggingConfig) -> dict:
    activity = config.activity
    sinks = ["console", "file"]
    with_activity = [*sinks, "activity"] if activity.enabled else sinks

    handlers: dict = {
        "console": {
            "class": "logging.StreamHandler",
            "level": config.console.log_level.value,
            "formatter": "console",
            "filters": ["log_context"],
            "stream": "ext://sys.stdout",
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "level": config.file.log_level.value,
            "formatter": "file",
            "filters": ["log_context"],
            "filename": config.file.file_name,
            "mode": "a",
            "maxBytes": 1 * 1024 * 1024,
            "backupCount": 2,
            "encoding": "utf_8",
            "delay": False,
        },
    }
    service_levels = [config.console.log_level.value, config.file.log_level.value]
    if activity.enabled:
        handlers["activity"] = {
            "()": "testbench_ai_service.log.build_activity_handler",
            "level": activity.log_level.value,
            "file_name": activity.file_name,
            "max_bytes": activity.max_bytes,
            "backup_count": activity.backup_count,
        }
        service_levels.append(activity.log_level.value)

    return {
        "version": 1,
        "disable_existing_loggers": True,
        "filters": {
            "log_context": {
                "()": "testbench_ai_service.log.LogContextFilter",
            }
        },
        "formatters": {
            "console": {
                "()": "testbench_ai_service.log.ColoredFormatter",
                "format": config.console.log_format,
            },
            "file": {"format": config.file.log_format},
        },
        "handlers": handlers,
        "loggers": {
            "testbench_ai_service": {
                "handlers": with_activity,
                "level": min(get_log_level_int(level) for level in service_levels),
                "propagate": False,
            },
            "uvicorn": {
                "handlers": with_activity,
                "level": config.console.log_level.value,
                "propagate": False,
            },
            "uvicorn.access": {
                "handlers": sinks,
                "level": config.console.log_level.value,
                "propagate": False,
            },
            "uvicorn.error": {
                "handlers": with_activity,
                "level": config.console.log_level.value,
                "propagate": False,
            },
            "uvicorn.asgi": {
                "handlers": sinks,
                "level": config.console.log_level.value,
                "propagate": False,
            },
            "py.warnings": {
                "handlers": sinks,
                "level": LogLevel.WARNING.value,
            },
        },
    }


def get_log_level_int(level_str: str, default: int = logging.INFO) -> int:
    level = getattr(logging, level_str.upper(), default)
    return int(level)


logging.captureWarnings(True)

logger = logging.getLogger("testbench_ai_service")
