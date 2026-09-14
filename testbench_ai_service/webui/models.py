from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from testbench_ai_service.models.config import PromptVarValue
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


class PromptMessageDoc(BaseModel):
    """One message, with its body resolved whether inline or external.

    Defined here (Task 5) rather than in Task 6, which uses it, because Task 5's
    renderer needs the type first. Task 6 does not redefine it.
    """

    role: Literal["system", "user", "assistant"] = "user"
    source: Literal["inline", "file"] = "inline"
    #: The reference as written in the YAML, when source is "file".
    file: str | None = None
    content: str = ""
    #: False when source is "file" but the file could not be read. The document
    #: still loads, so the operator can see and repair the broken reference.
    readable: bool = True


class LintError(BaseModel):
    """One Jinja syntax error, addressed for an editor gutter."""

    line: int
    column: int
    message: str


class LintResponse(BaseModel):
    ok: bool
    #: Jinja reports one TemplateSyntaxError at a time, so this holds zero or
    #: one entry. It is a list because that is the shape an editor's diagnostic
    #: API wants, and widening it later would be a breaking change.
    errors: list[LintError] = []


class RenderedMessage(BaseModel):
    role: str
    content: str
    error: str | None = None


class RenderResponse(BaseModel):
    messages: list[RenderedMessage] = []


class PromptUsage(BaseModel):
    """One config key pointing at a prompt file.

    Structured rather than pre-rendered prose: the console defaults to German,
    so the caller localizes "the global agents table" / "project 'X'". Only the
    project NAME survives untranslated, the way an agent key does.
    """

    agent: str
    #: None for the global agents table, otherwise the project's raw name.
    project: str | None = None


class PromptTreeEntry(BaseModel):
    """One agent's prompt, as the tree screen lists it."""

    agent: str
    #: Relative to prompts_dir -- the spelling an operator writes in config.toml.
    file: str
    name: str | None = None
    variants: list[str] = []
    #: False when the file is there but did not parse. The entry is still
    #: listed: an operator who cannot see a broken prompt cannot fix it either.
    ok: bool = True
    error: str | None = None
    #: Which config keys resolve to this file. A labelling nicety, not part of
    #: the tree's own identity -- an unreadable config.toml leaves this empty
    #: rather than hiding the entry itself.
    used_by: list[PromptUsage] = []


class PromptTreeLanguage(BaseModel):
    lang: str
    prompts: list[PromptTreeEntry] = []


class PromptTreeResponse(BaseModel):
    languages: list[PromptTreeLanguage] = []


class PromptVariantDoc(BaseModel):
    name: str
    description: str | None = None
    model: str | None = None
    vars: dict[str, PromptVariableDefinition] = {}
    messages: list[PromptMessageDoc] = []


class PromptDocumentResponse(BaseModel):
    lang: str
    agent: str
    file: str
    name: str
    summary: str | None = None
    description: str | None = None
    default_model: str
    default_variant: str
    variants: list[PromptVariantDoc] = []
    #: Nested skeleton of every agent.* path the templates reference, for the
    #: render pane to prefill. Computed from the real Jinja AST server-side.
    agent_context_skeleton: dict[str, Any] = {}


class PromptSaveRequest(BaseModel):
    name: str
    summary: str | None = None
    description: str | None = None
    default_model: str
    default_variant: str
    variants: list[PromptVariantDoc] = []


class PromptSaveResponse(BaseModel):
    #: Every file written -- created and updated alike.
    written: list[str] = []
    #: The subset of *written* that did not exist before.
    created: list[str] = []
    deleted: list[str] = []
    deletions_skipped: str | None = None
    backups: list[str] = []


class PromptPlanResponse(BaseModel):
    """What a save would do, without doing it."""

    created: list[str] = []
    updated: list[str] = []
    deleted: list[str] = []
    #: Why nothing is being deleted, when the tree scan could not be trusted.
    deletions_skipped: str | None = None


class PromptForkRequest(BaseModel):
    project: str = Field(min_length=1)
    #: The operator's correction to the final path segment alone, never a path.
    directory: str | None = None


class PromptForkResponse(BaseModel):
    lang: str
    agent: str
    file: str
    created: list[str] = []
    config_backup: str | None = None
    reloaded: bool = False


class LintRequest(BaseModel):
    content: str


class RenderRequest(BaseModel):
    messages: list[PromptMessageDoc] = []
    vars: dict[str, PromptVarValue] = {}
    agent_context: dict[str, Any] = {}
