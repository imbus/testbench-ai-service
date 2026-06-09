import importlib
import inspect
from pathlib import Path
from typing import Any, get_type_hints

from pydantic import BaseModel, Field, field_validator, model_validator

from testbench_ai_service.models.config import (
    AgentConfig,
    LLMConfig,
    ProjectConfig,
    PromptConfig,
)
from testbench_ai_service.models.language import LanguageOption
from testbench_ai_service.models.logging import LoggingConfig
from testbench_ai_service.utils.prompt_utils import template_variables, validate_template
from testbench_ai_service.validators import (
    raise_field_validation_error,
    validate_prompt_file,
    validate_tb_server_url,
)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8010
PROMPTS_DIR = (Path(__file__).parent / "prompts").resolve()
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
    language: LanguageOption = LanguageOption.GERMAN
    llm_config: LLMConfig = Field(default_factory=LLMConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    agents: dict[str, AgentConfig] = DEFAULT_AGENTS
    projects: dict[str, ProjectConfig] = Field(default_factory=dict)

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

    @model_validator(mode="after")
    def validate_prompt_paths(self):
        """Validate and resolve all prompt file paths."""
        for agent_key, agent in self.agents.items():
            try:
                validate_prompt_file(
                    agent.prompt.file,
                    prompts_dir=self.prompts_dir,
                    language=self.language.value,
                )
            except ValueError as e:
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
                prompt_variant=agent.prompt.variant,
            )
            agent_data = {}
            for _, obj in inspect.getmembers(module):
                if inspect.isclass(obj) and hasattr(obj, "AGENT_DATA_CLASS"):
                    agent_data = get_type_hints(obj.AGENT_DATA_CLASS)

            if not validate_template(user_variables, agent_data):
                raise Exception
        return self
