from enum import Enum

from pydantic import BaseModel, Field

DEFAULT_MAX_PAYLOAD_LENGTH = 4000


class LogLevel(str, Enum):
    CRITICAL = "CRITICAL"
    FATAL = CRITICAL
    ERROR = "ERROR"
    WARNING = "WARNING"
    WARN = WARNING
    INFO = "INFO"
    DEBUG = "DEBUG"
    VERBOSE = "VERBOSE"
    NOTSET = "NOTSET"


class ConsoleLoggerConfig(BaseModel):
    log_level: LogLevel = LogLevel.INFO
    log_format: str = "%(asctime)s -%(levelname)s: %(message)s"


class FileLoggerConfig(BaseModel):
    file_name: str = "testbench-ai-service.log"
    log_level: LogLevel = LogLevel.INFO
    log_format: str = "%(asctime)s - %(levelname)8s - %(name)s - %(message)s"


class LoggingConfig(BaseModel):
    console: ConsoleLoggerConfig = Field(default_factory=ConsoleLoggerConfig)
    file: FileLoggerConfig = Field(default_factory=FileLoggerConfig)
    max_payload_length: int = Field(
        default=DEFAULT_MAX_PAYLOAD_LENGTH,
        ge=0,
        description="Maximum number of characters logged per payload. 0 means no truncation.",
    )
