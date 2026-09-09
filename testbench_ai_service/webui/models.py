from typing import Any

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class SessionResponse(BaseModel):
    """Identity of the current console user. Deliberately carries no token."""

    username: str
    roles: list[str]
    is_admin: bool
    tb_server_url: str


class MetaResponse(BaseModel):
    """The only unauthenticated payload: which TestBench this service signs into.

    The login screen needs it before a session can exist. Nothing else belongs
    here.
    """

    tb_server_url: str


class ServiceStatus(BaseModel):
    version: str
    host: str
    port: int
    debug: bool
    uptime_seconds: float
    language: str


class TestBenchStatus(BaseModel):
    url: str
    reachable: bool
    detail: str | None = None


class ApiKeyStatus(BaseModel):
    """Whether a provider credential is configured. Never its value."""

    name: str
    present: bool


class AgentSummary(BaseModel):
    total: int
    enabled: int
    project_overrides: int
    projects: int


class StatusResponse(BaseModel):
    service: ServiceStatus
    testbench: TestBenchStatus
    api_keys: list[ApiKeyStatus]
    agents: AgentSummary
    log_file: str
    in_flight_tasks: int = 0


class ConfigResponse(BaseModel):
    """The service's configuration, as loaded and as stored.

    ``running`` is what the process is using; ``disk`` is what the file says.
    """

    running: dict
    disk: dict
    config_path: str


class LogLine(BaseModel):
    """One parsed log record. Unparseable lines keep only ``raw``."""

    raw: str
    timestamp: str | None = None
    level: str | None = None
    source: str | None = None
    message: str


class ConfigIssue(BaseModel):
    """One validation failure, addressed to the field that caused it.

    ``path`` is the dotted config path the console's form fields are keyed by,
    so the UI can mark the offending input. ``toml_section`` is the same
    location spelled the way it appears in ``config.toml``, for the operator
    who would rather fix the file by hand.
    """

    path: str
    message: str
    toml_section: str


class FileDiff(BaseModel):
    """A unified diff for one file the console proposes to write."""

    path: str
    diff: str
    added: int
    removed: int


class ConfigEditsRequest(BaseModel):
    """A sparse overlay of dotted config paths to new values.

    A ``None`` value removes the key so the model default takes over again.
    The browser posts only what the operator changed, never a whole config --
    see the module docstring of ``webui/edits.py`` for why.
    """

    edits: dict[str, Any] = Field(default_factory=dict)


class PreviewResponse(BaseModel):
    """What applying the current overlay would do, without doing it."""

    valid: bool
    issues: list[ConfigIssue]
    diffs: list[FileDiff]
    restart_required: list[str]
    in_flight_tasks: int
    # The rendered config.toml the apply would write. Also what the Raw screen
    # shows, which is why it is here rather than on a route of its own.
    toml: str


class ApplyResponse(BaseModel):
    """What an apply actually did."""

    written: list[str]
    backup: str | None
    restart_required: list[str]
    reloaded: bool
    in_flight_tasks: int
