from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from testbench_ai_service.llm.base import LLMProvider
from testbench_ai_service.models.language import LanguageOption
from testbench_ai_service.models.logging import LoggingConfig
from testbench_ai_service.validators import (
    raise_field_validation_error,
    validate_custom_class_path,
    validate_prompt_file,
    validate_tb_server_url,
)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8010
PROMPTS_DIR = (Path(__file__).parent / "prompts").resolve()


class LLMConfig(BaseModel):
    provider: LLMProvider = LLMProvider.OPENAI
    model: str | None = None
    azure_endpoint: str | None = None
    api_version: str | None = None
    class_path: str | None = None

    model_config = ConfigDict(extra="allow")

    @model_validator(mode="after")
    def validate_config(self):
        if self.provider == LLMProvider.CUSTOM:
            try:
                validate_custom_class_path(self.class_path)
            except ValueError as e:
                raise_field_validation_error(self, "class_path", e)

        if self.provider == LLMProvider.AZURE_OPENAI:
            if not self.azure_endpoint:
                raise_field_validation_error(
                    self,
                    "azure_endpoint",
                    ValueError("'azure_endpoint' must be set for provider 'azure_openai'."),
                )
            if not self.api_version:
                raise_field_validation_error(
                    self,
                    "api_version",
                    ValueError("'api_version' must be set for provider 'azure_openai'."),
                )
        return self


class PromptConfig(BaseModel):
    file: Path
    name: str
    variant: str | None = None
    placeholder_data: dict[str, str] | None = None

    model_config = ConfigDict(extra="allow")


class ProjectPromptConfig(BaseModel):
    file: Path | None = None
    name: str | None = None
    variant: str | None = None
    placeholder_data: dict[str, str] | None = None


class AgentConfig(BaseModel):
    enabled: bool
    endpoint_path: str
    class_path: str
    prompt: PromptConfig
    name: str
    summary: str | None = None
    description: str | None = None

    # @field_validator("class_path", mode="after")
    # @classmethod
    # def validate_config(cls, value: str):
    #     return validate_custom_class_path(value)


class ProjectAgentConfig(BaseModel):
    enabled: bool | None = None
    prompt: ProjectPromptConfig | None = None


class ProjectConfig(BaseModel):
    language: LanguageOption | None = None
    llm_config: LLMConfig | None = None
    agents: dict[str, ProjectAgentConfig] | None = None


DEFAULT_AGENTS: dict[str, AgentConfig] = {
    "test_case_set_reviewer": AgentConfig(
        enabled=True,
        endpoint_path="/test-case-set-reviews",
        class_path="testbench_ai_service.agents.test_case_set_reviewer.agent.TestCaseSetReviewer",
        prompt=PromptConfig(
            file=Path("test_case_set_reviewer.yaml"),
            name="TestCaseSetReviewer",
        ),
        name="Test Case Set Reviewer",
        summary="Trigger test case set reviews",
        description="""This endpoint triggers asynchronous reviews for the specified test case sets.
            The review results will be added as comments to the `reviewComment` attribute (review comments section) of corresponding test structure element specifications.""",
    ),
    "test_case_set_describer": AgentConfig(
        enabled=True,
        endpoint_path="/test-case-set-descriptions",
        class_path="testbench_ai_service.agents.test_case_set_describer.agent.TestCaseSetDescriber",
        prompt=PromptConfig(
            file=Path("test_case_set_describer.yaml"),
            name="TestCaseSetDescriber",
        ),
        name="Test Case Set Describer",
        summary="Trigger generation of test case set descriptions",
        description="""This endpoint triggers asynchronous generation of descriptions for the specified test case sets.
            The generated descriptions will be assigned to their respective test structure element specifications.""",
    ),
    "defect_explainer": AgentConfig(
        enabled=True,
        endpoint_path="/defect-explanations",
        class_path="testbench_ai_service.agents.defect_explainer.agent.DefectExplainer",
        prompt=PromptConfig(
            file=Path("defect_explainer.yaml"),
            name="DefectExplainer",
        ),
        name="Defect Explainer",
        summary="Trigger generation of defect explanations",
        description="""This endpoint triggers asynchronous generation of defect explanations for the specified test case sets.
            The generated explanations will be added to the comment section of the corresponding test structure element execution overview.""",
    ),
}


class AppConfig(BaseModel):
    tb_server_url: str = Field(
        "https://localhost:9443/api/",
        description="Base URL of the TestBench REST API server",
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

    @field_validator("ssl_cert", "ssl_key", "ssl_ca_cert")
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
                    name=agent.prompt.name,
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
                        name=agent_override.prompt.name,
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
