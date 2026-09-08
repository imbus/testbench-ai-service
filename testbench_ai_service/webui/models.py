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


class LogLine(BaseModel):
    """One parsed log record. Unparseable lines keep only ``raw``."""

    raw: str
    timestamp: str | None = None
    level: str | None = None
    source: str | None = None
    message: str
