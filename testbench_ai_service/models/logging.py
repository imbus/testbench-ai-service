from enum import Enum

from pydantic import BaseModel, Field


class LogLevel(str, Enum):
    CRITICAL = "CRITICAL"
    FATAL = CRITICAL
    ERROR = "ERROR"
    WARNING = "WARNING"
    WARN = WARNING
    INFO = "INFO"
    DEBUG = "DEBUG"
    NOTSET = "NOTSET"


class ConsoleLoggerConfig(BaseModel):
    log_level: LogLevel = LogLevel.INFO
    log_format: str = "%(asctime)s -%(levelname)s: %(message)s"


class FileLoggerConfig(BaseModel):
    file_name: str = "testbench-ai-service.log"
    log_level: LogLevel = LogLevel.INFO
    log_format: str = "%(asctime)s - %(levelname)8s - %(name)s - %(message)s"


class ActivityLoggerConfig(BaseModel):
    """The structured sink the console's activity view reads (design D5)."""

    enabled: bool = True
    file_name: str = "testbench-ai-service.activity.jsonl"
    log_level: LogLevel = LogLevel.INFO
    max_bytes: int = Field(default=5 * 1024 * 1024, gt=0)
    backup_count: int = Field(default=3, ge=0)


class LoggingConfig(BaseModel):
    console: ConsoleLoggerConfig = Field(default_factory=ConsoleLoggerConfig)
    file: FileLoggerConfig = Field(default_factory=FileLoggerConfig)
    activity: ActivityLoggerConfig = Field(default_factory=ActivityLoggerConfig)
