from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from testbench_ai_service.llm.base import LLMProvider, RoutingFamily, TokenUsage
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
    has_user_key: bool = False


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
    # When this app was built; a restart from the console changes it.
    started_at: datetime
    # Whether the console can restart the service (see testbench_ai_service.restart).
    can_restart: bool = False


class RestartResponse(BaseModel):
    """Where the service will listen once the restart requested is done."""

    host: str
    port: int
    tls: bool
    in_flight_tasks: int = 0


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
    # Agent package name -> why it is not in use (failed, or needs a restart).
    unloaded_packages: dict[str, str] = {}
    # Agent key -> why its class failed to import at startup (it has no route).
    failed_agents: dict[str, str] = {}


class ModelUsageEntry(BaseModel):
    provider: str
    model: str
    calls: int
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    last_used: datetime


class UsageSummary(BaseModel):
    """Token totals per model since the usage file was created."""

    available: bool = True
    models: list[ModelUsageEntry] = []


class StatusResponse(BaseModel):
    service: ServiceStatus
    testbench: TestBenchStatus
    api_keys: list[ApiKeyStatus]
    agents: AgentSummary
    in_flight_tasks: int = 0
    restart_required: list[str] = []
    token_usage: UsageSummary = Field(default_factory=UsageSummary)
    llm_client_error: str | None = Field(
        default=None,
        description="Why the LLM client an uploaded package provides is not in use.",
    )


class ConfigResponse(BaseModel):
    """The service's configuration, as loaded and as stored.

    ``running`` is what the process is using; ``disk`` is what the file says.
    ``effective`` is what the file amounts to once the defaults are filled in:
    the configuration the service would run after a restart. It differs from
    ``running`` exactly while a restart is pending, and is what a form shows
    for a key the file does not set -- showing ``running`` there would present
    a setting that was just removed as if it were still in force.
    """

    running: dict
    disk: dict
    effective: dict
    config_path: str


class RawConfigResponse(BaseModel):
    """``config.toml`` as it is on disk, credentials replaced by the sentinel."""

    toml: str


class ActivityEntry(BaseModel):
    """One activity record as the console shows it.

    Carries no user identity: a user only ever sees their own entries and
    service entries (design D6), so naming the user would add nothing but a
    leak if that rule were ever broken.
    """

    timestamp: str
    level: str
    source: str
    message: str
    scope: Literal["user", "service"]
    agent: str | None = None
    project_key: str | None = None
    run_id: str | None = None
    exc: str | None = None


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
    toml: str


class ApplyResponse(BaseModel):
    """What an apply actually did."""

    written: list[str]
    backup: str | None
    restart_required: list[str]
    reloaded: bool
    in_flight_tasks: int
    reload_detail: str | None = None


class PromptMessageDoc(BaseModel):
    """One message, with its body resolved whether inline or external.

    Defined here (Task 5) rather than in Task 6, which uses it, because Task 5's
    renderer needs the type first. Task 6 does not redefine it.
    """

    role: Literal["system", "user", "assistant"] = "user"
    source: Literal["inline", "file"] = "inline"
    file: str | None = None
    content: str = ""
    readable: bool = True

    @field_validator("content")
    @classmethod
    def _line_feeds_only(cls, value: str) -> str:
        """A message body always uses ``\\n`` in transit.

        An editor on Windows starts a new, empty buffer with CRLF, so a freshly
        typed message arrived with ``\\r\\n``: YAML then cannot write it as a
        block and falls back to one escaped line, and the carriage returns would
        reach the model. What a file is written with is decided at the write,
        from the file itself.
        """
        return value.replace("\r\n", "\n").replace("\r", "\n")


class LintError(BaseModel):
    """One Jinja syntax error, addressed for an editor gutter."""

    line: int
    column: int
    message: str


class LintResponse(BaseModel):
    ok: bool
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
    project: str | None = None


class PromptTreeEntry(BaseModel):
    """One agent's prompt, as the tree screen lists it."""

    agent: str
    file: str
    name: str | None = None
    variants: list[str] = []
    ok: bool = True
    error: str | None = None
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
    steps: dict[str, list[PromptMessageDoc]] = {}


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
    agent_context_skeleton: dict[str, Any] = {}
    agent_context_sample: dict[str, Any] = {}
    # sha256 of prompt.yaml and of every template it references, by path, as read
    # for this response. The editor hands them back with a save.
    revisions: dict[str, str] = {}
    # Keys in prompt.yaml the prompt format does not know, as dotted paths. They
    # are ignored when the prompt runs and are not written back by a save.
    unknown_keys: list[str] = []


class PromptSaveRequest(BaseModel):
    name: str
    summary: str | None = None
    description: str | None = None
    default_model: str
    default_variant: str
    variants: list[PromptVariantDoc] = []
    # The ``revisions`` of the document this save was edited from. With them, a file
    # that changed on disk in the meantime is reported instead of overwritten.
    revisions: dict[str, str] | None = None
    # Set once the operator has seen that report and wants the save anyway.
    overwrite_changed: bool = False


class PromptSaveResponse(BaseModel):
    written: list[str] = []
    created: list[str] = []
    deleted: list[str] = []
    deletions_skipped: str | None = None
    backups: list[str] = []


class PromptPlanResponse(BaseModel):
    """What a save would do, without doing it."""

    created: list[str] = []
    updated: list[str] = []
    deleted: list[str] = []
    deletions_skipped: str | None = None
    # Files the save would write or remove that changed on disk since the editor
    # loaded them: saving replaces someone else's change.
    changed_on_disk: list[str] = []


class PromptForkTarget(BaseModel):
    """Where a fork for one project would go when no directory is named."""

    directory: str
    exists: bool


class PromptForkRequest(BaseModel):
    project: str = Field(min_length=1)
    directory: str | None = None


class PromptForkResponse(BaseModel):
    lang: str
    agent: str
    file: str
    created: list[str] = []
    config_backup: str | None = None
    reloaded: bool = False
    reload_detail: str | None = None


class LintRequest(BaseModel):
    content: str


class RenderRequest(BaseModel):
    messages: list[PromptMessageDoc] = []
    vars: dict[str, PromptVarValue] = {}
    agent_context: dict[str, Any] = {}


class CatalogueModel(BaseModel):
    """One offerable model and the request shape it will be called with."""

    id: str
    routing: RoutingFamily
    source: Literal["builtin", "config"]


class CatalogueProvider(BaseModel):
    provider: LLMProvider
    key_present: bool
    models: list[CatalogueModel]


class ModelCatalogueResponse(BaseModel):
    providers: list[CatalogueProvider]


class PromptTestRequest(RenderRequest):
    """A render request plus where to send the result.

    Inherits RenderRequest deliberately: the preview pane and the test run
    must send the same messages, vars and agent_context, or the operator
    tested something other than what they saw (design D1).
    """

    model: str
    project: str | None = None


class ResolvedRoute(BaseModel):
    provider: LLMProvider
    model: str
    credential_scope: Literal["project", "global"]


class PromptTestResponse(BaseModel):
    text: str
    latency_ms: int
    usage: TokenUsage | None = None
    resolved: ResolvedRoute
