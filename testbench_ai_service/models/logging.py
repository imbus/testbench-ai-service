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
    log_format: str = "%(levelname)s: %(message)s"


class FileLoggerConfig(BaseModel):
    file_name: str = "testbench-ai-service.log"
    log_level: LogLevel = LogLevel.INFO
    log_format: str = "%(asctime)s - %(levelname)8s - %(name)s - %(message)s"


class LoggingConfig(BaseModel):
    console: ConsoleLoggerConfig = Field(default_factory=ConsoleLoggerConfig)
    file: FileLoggerConfig = Field(default_factory=FileLoggerConfig)
