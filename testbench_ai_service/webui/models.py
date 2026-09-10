from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from testbench_ai_service.models.prompt import PromptVariableDefinition


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


class ProjectRef(BaseModel):
    """One TestBench project, named the way ``config.toml`` keys it.

    ``name`` is the raw TestBench project name -- spaces, dots and all -- because
    that is exactly the string a ``[projects."<name>"]`` block must use.
    """

    name: str
    key: str


class ProjectsResponse(BaseModel):
    """The console's view of the TestBench project list.

    ``source`` is what the Projects screen keys its fallback off: on
    ``"unavailable"`` it offers a free-text "add project by name" field, because
    an empty list is then an absence of information rather than an answer.
    ``fetched_at`` is surfaced so the operator can see how stale the cache is --
    it can be up to the session's absolute cap old.
    """

    projects: list[ProjectRef]
    fetched_at: datetime | None = None
    source: Literal["testbench", "unavailable"]
    error: str | None = None


class PromptVariantMeta(BaseModel):
    """One variant of a prompt, without any of its message templates.

    ``model`` is reported exactly as the variant declares it, ``None``
    included: the fallback to the prompt's ``default_model`` is the console's to
    display, and resolving it here would hide that the variant pins no model of
    its own.
    """

    name: str
    description: str | None = None
    model: str | None = None
    vars: dict[str, PromptVariableDefinition] = {}


class PromptMetaResponse(BaseModel):
    """What the agent-detail form needs from a prompt file, and nothing more.

    The variant list turns ``prompt.variant`` from typo-prone free text into a
    select, and each variable's ``value_type``/``choices`` decide which widget
    renders its value. Message bodies and template files are deliberately
    absent -- they belong to phase 4's editor.
    """

    name: str
    summary: str | None = None
    description: str | None = None
    default_model: str
    default_variant: str
    variants: list[PromptVariantMeta]


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
    restart_required: list[str] = []


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
    # Populated only when `reloaded` is False for a reason other than a
    # required restart (`restart_required` already explains that case). If
    # the failure is the log path itself, the service log may be exactly what
    # cannot be written to -- this field is then the operator's only channel.
    reload_detail: str | None = None
