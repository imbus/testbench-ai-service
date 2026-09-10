import importlib
import inspect
from pathlib import Path
from typing import Any, get_type_hints

from pydantic import BaseModel, Field, field_validator, model_validator

from testbench_ai_service.log import logger
from testbench_ai_service.models.config import (
    AgentConfig,
    LLMConfig,
    ProjectConfig,
    PromptConfig,
)
from testbench_ai_service.models.language import LanguageOption
from testbench_ai_service.models.logging import LoggingConfig
from testbench_ai_service.models.webui import AdminUiConfig
from testbench_ai_service.transport import (
    DEFAULT_CONNECT_TIMEOUT,
    DEFAULT_MAX_RETRIES,
    DEFAULT_READ_TIMEOUT,
)
from testbench_ai_service.utils.prompt_utils import (
    template_variables,
    validate_agent_variable,
)
from testbench_ai_service.validators import (
    raise_field_validation_error,
    resolve_prompt_file_path,
    validate_prompt_file,
    validate_tb_server_url,
)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8010
PROMPTS_DIR = (Path(__file__).parent / "prompts").resolve()
TEMPLATES_DIR = (Path(__file__).parent / "templates").resolve()

DEFAULT_AGENTS: dict[str, AgentConfig] = {
    "test_case_set_reviewer": AgentConfig(
        enabled=True,
        endpoint_path="/test-case-set-reviews",
        class_path="testbench_ai_service.agents.test_case_set_reviewer.agent.TestCaseSetReviewer",
        prompt=PromptConfig(
            file=Path("test_case_set_reviewer/prompt.yaml"),
        ),
    ),
    "test_case_set_describer": AgentConfig(
        enabled=True,
        endpoint_path="/test-case-set-descriptions",
        class_path="testbench_ai_service.agents.test_case_set_describer.agent.TestCaseSetDescriber",
        prompt=PromptConfig(
            file=Path("test_case_set_describer/prompt.yaml"),
        ),
    ),
    "defect_explainer": AgentConfig(
        enabled=True,
        endpoint_path="/defect-explanations",
        class_path="testbench_ai_service.agents.defect_explainer.agent.DefectExplainer",
        prompt=PromptConfig(
            file=Path("defect_explainer/prompt.yaml"),
        ),
    ),
}


def _prompt_file_is_absent(file: Path, prompts_dir: Path | None, language: str) -> bool:
    """Whether *file* cannot be found at all, as opposed to being unreadable.

    ``validate_prompt_file`` raises the same ``ValueError`` for a file that is
    missing and for one that is present but malformed. Only the first is a
    reason to treat an agent as simply not installed.
    """
    try:
        resolve_prompt_file_path(file, prompts_dir=prompts_dir, language=language)
    except ValueError:
        return True
    return False


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Merge *override* into *base*, recursing into nested tables.

    Neither argument is mutated. A non-table value replaces whatever is at that
    key; two tables are merged key by key, so ``{"prompt": {"variant": "x"}}``
    sets the variant without discarding the prompt's ``file``.
    """
    merged = dict(base)
    for key, value in override.items():
        existing = merged.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            merged[key] = _deep_merge(existing, value)
        else:
            merged[key] = value
    return merged


class AppConfig(BaseModel):
    tb_server_url: str = Field(
        "https://localhost:9443/api/",
        description="Base URL of the TestBench REST API server",
    )
    tb_ssl_verify: bool = Field(
        True,
        description="Verify the SSL/TLS certificate of the TestBench server. Set to False to disable verification (insecure).",
    )
    tb_ssl_ca_bundle: str | None = Field(
        default=None,
        description="Path to a CA bundle file used to verify the TestBench server certificate. When set, takes precedence over tb_ssl_verify.",
    )
    tb_connect_timeout: float = Field(
        DEFAULT_CONNECT_TIMEOUT,
        gt=0,
        description="Seconds to wait while establishing a connection to the TestBench server.",
    )
    tb_read_timeout: float = Field(
        DEFAULT_READ_TIMEOUT,
        gt=0,
        description="Seconds to wait for data from the TestBench server before giving up. Bounds requests that would otherwise stall indefinitely.",
    )
    tb_max_retries: int = Field(
        DEFAULT_MAX_RETRIES,
        ge=0,
        description="How often to retry a TestBench request that failed with a connection error. Only idempotent methods are retried; POST and PATCH are never replayed.",
    )
    host: str = Field(
        DEFAULT_HOST,
        description="Hostname or IP address to run the service on",
    )
    port: int = Field(
        DEFAULT_PORT,
        description="Port number to run the service on",
    )
    debug: bool = Field(False, description="Enable debug mode for the service")
    ssl_cert: str | None = Field(
        default=None,
        description="Path to SSL/TLS certificate file for HTTPS support",
    )
    ssl_key: str | None = Field(
        default=None,
        description="Path to SSL/TLS private key file for HTTPS support",
    )
    ssl_ca_cert: str | None = Field(
        default=None,
        description="Path to CA certificate file for client verification",
    )
    trusted_proxies: list[str] | None = Field(
        default=None,
        description="List of trusted proxy IPs for proper client IP forwarding",
    )
    prompts_dir: Path | None = Field(
        default=PROMPTS_DIR,
        description="Directory containing prompt YAML files. Relative paths in prompt configs are resolved against this base directory.",
    )
    templates_dir: Path | None = Field(
        default=TEMPLATES_DIR,
        description="Directory containing jinja templates for agents.",
    )
    language: LanguageOption = LanguageOption.GERMAN
    llm_config: LLMConfig = Field(default_factory=LLMConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    admin_ui: AdminUiConfig = Field(
        default_factory=AdminUiConfig,
        description="Browser console served at /admin",
    )
    agents: dict[str, AgentConfig] = DEFAULT_AGENTS
    projects: dict[str, ProjectConfig] = Field(default_factory=dict)
    loaded_from: Path | None = Field(
        default=None,
        exclude=True,
        description="Path this config was loaded from; set by load_config_from_file",
    )

    @field_validator("agents", mode="before")
    @classmethod
    def merge_agents_onto_defaults(cls, agents: Any) -> Any:
        """Let a partial ``[agents.<key>]`` block override one setting.

        Without this, ``agents`` is a plain replacement: every ``AgentConfig``
        field is required, so ``enabled = false`` on its own fails validation,
        and spelling the block out in full drops every agent the operator did
        not mention. There was no way to express "turn this agent off".

        A key that names a built-in is merged onto that built-in, recursively,
        so ``[agents.x.prompt] variant = "..."`` keeps the prompt's ``file``. A
        key that names no built-in is passed through untouched and must still
        be declared in full -- there is nothing to inherit from.

        Merging happens *before* validation on plain dicts, rather than through
        ``model_copy(update=...)`` on the built model: ``model_copy`` neither
        validates nor recurses, so a nested partial would leave ``prompt`` as a
        raw dict and every ``agent.prompt.file`` lookup would raise.
        """
        if not isinstance(agents, dict):
            return agents

        # Start from every built-in, so an agent the operator did not mention
        # survives. model_dump() builds a fresh dict every call, so the shared
        # DEFAULT_AGENTS models are never touched.
        merged: dict[Any, Any] = {
            key: default.model_dump() for key, default in DEFAULT_AGENTS.items()
        }
        for key, override in agents.items():
            default = DEFAULT_AGENTS.get(key)
            if default is None:
                merged[key] = override
                continue
            # A Python caller passes AgentConfig objects; TOML gives dicts.
            fields = override.model_dump() if isinstance(override, BaseModel) else override
            if not isinstance(fields, dict):
                merged[key] = override
                continue
            merged[key] = _deep_merge(merged[key], fields)
        return merged

    @field_validator("tb_server_url", mode="after")
    @classmethod
    def validate_url(cls, tb_server_url: str):
        validate_tb_server_url(tb_server_url)
        return tb_server_url

    @field_validator("ssl_cert", "ssl_key", "ssl_ca_cert", "tb_ssl_ca_bundle")
    @classmethod
    def validate_ssl_files_exist(cls, v: str | None) -> str | None:
        """Validate that SSL certificate files exist if provided."""
        if v is not None and not Path(v).exists():
            raise ValueError(f"SSL certificate file not found: '{v}'")
        return v

    @field_validator("trusted_proxies", mode="before")
    @classmethod
    def validate_trusted_proxies(cls, v: Any) -> list[str] | None:
        """Validate and normalize trusted proxies input."""
        if not v:
            return None
        if isinstance(v, str):
            return [ip.strip() for ip in v.split(",") if ip.strip()]
        if isinstance(v, list):
            return v
        raise ValueError("trusted_proxies must be a list of strings or a comma-separated string")

    @field_validator("prompts_dir")
    @classmethod
    def validate_prompts_dir_exists(cls, v: Path | None) -> Path | None:
        """Validate that the prompts directory exists if provided."""
        if v is not None:
            if not v.exists():
                raise ValueError(f"Prompts directory not found: '{v.resolve()}'")
            if not v.is_dir():
                raise ValueError(f"Prompts path is not a directory: '{v.resolve()}'")
        return v

    @field_validator("templates_dir")
    @classmethod
    def validate_templates_dir_exists(cls, v: Path | None) -> Path | None:
        """Validate that the templates directory exists if provided."""
        if v is not None:
            if not v.exists():
                raise ValueError(f"Templates directory not found: '{v.resolve()}'")
            if not v.is_dir():
                raise ValueError(f"Templates path is not a directory: '{v.resolve()}'")
        return v

    def _is_untouched_builtin(self, agent_key: str, agent: AgentConfig) -> bool:
        """Whether *agent* is a built-in the operator's config left alone.

        Compares the merged entry against the built-in rather than tracking
        which keys the operator wrote: a block that spells the default out
        again means the same thing as no block at all.
        """
        return agent == DEFAULT_AGENTS.get(agent_key)

    @model_validator(mode="after")
    def validate_prompt_paths(self):
        """Validate and resolve all prompt file paths.

        Two agents are exempt, because for them a prompt file is not something
        the operator asked for:

        * a **disabled** agent -- it gets no endpoint, so requiring its prompt
          file to exist would make ``enabled = false`` an incomplete off
          switch, and that is the documented way to withdraw an agent;
        * an **untouched built-in whose prompt file is absent** -- since the
          ``agents`` table merges onto the built-ins, every config carries all
          three, including one whose ``prompts_dir`` holds only the operator's
          own prompts. Failing there would refuse to start a service that
          started before the merge, naming an agent the operator never wrote
          down. It is dropped with a warning instead: it cannot run, and that
          is exactly the state such a config was in before.
        """
        for agent_key, agent in list(self.agents.items()):
            if not agent.enabled:
                continue
            try:
                validate_prompt_file(
                    agent.prompt.file,
                    prompts_dir=self.prompts_dir,
                    language=self.language.value,
                )
            except ValueError as e:
                if self._is_untouched_builtin(agent_key, agent) and _prompt_file_is_absent(
                    agent.prompt.file, self.prompts_dir, self.language.value
                ):
                    logger.warning(
                        "Built-in agent '%s' is not configured and its prompt file '%s' was not "
                        "found under '%s'. The agent is unavailable. Configure it explicitly if "
                        "you meant to run it; otherwise this message can be ignored.",
                        agent_key,
                        agent.prompt.file,
                        self.prompts_dir,
                    )
                    del self.agents[agent_key]
                    continue
                raise_field_validation_error(self, ("agents", agent_key, "prompt", "file"), e)
        for proj_key, project in self.projects.items():
            for agent_key, agent_override in (project.agents or {}).items():
                if agent_override.prompt is None or agent_override.prompt.file is None:
                    continue
                try:
                    validate_prompt_file(
                        agent_override.prompt.file,
                        prompts_dir=self.prompts_dir,
                        language=self.language.value,
                    )
                except ValueError as e:
                    raise_field_validation_error(
                        self,
                        ("projects", proj_key, "agents", agent_key, "prompt", "file"),
                        e,
                    )
        return self

    @model_validator(mode="after")
    def validate_config(self):
        for _, agent in self.agents.items():
            # A disabled agent gets no router, so nothing here can go wrong at
            # runtime: importing its class and matching its template variables
            # would only be able to refuse a boot over an agent that is
            # switched off. Same reasoning as validate_prompt_paths.
            if not agent.enabled:
                continue

            if not agent.class_path:
                raise ValueError("'class_path' must be set.")

            try:
                module_path, class_name = agent.class_path.rsplit(".", 1)
            except ValueError as e:
                raise ValueError(
                    "'class_path' must be a valid import path, e.g. 'package.module.ClassName'."
                ) from e

            try:
                module = importlib.import_module(module_path)
                getattr(module, class_name)
            except (ImportError, AttributeError) as e:
                raise ValueError(f"cannot import '{class_name}' from '{module_path}': {e}") from e

            user_variables = template_variables(
                prompt_file=Path(self.prompts_dir, self.language.value, agent.prompt.file),
            )
            agent_data = {}
            for _, obj in inspect.getmembers(module):
                if inspect.isclass(obj) and hasattr(obj, "AGENT_DATA_CLASS"):
                    agent_data = get_type_hints(obj.AGENT_DATA_CLASS).keys()

            if not validate_agent_variable(user_variables, agent_data):
                logger.error(
                    "Template validation failed. User variables: %s do not match agent data requirements.",
                    user_variables,
                )
                raise ValueError(
                    "Failed to validate template: variables are incompatible with the agent."
                )
        return self
