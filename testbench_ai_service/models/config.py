from pathlib import Path

from pydantic import BaseModel, ConfigDict, model_validator

from testbench_ai_service.llm.base import AzureAuthMethod, LLMProvider
from testbench_ai_service.models.language import LanguageOption
from testbench_ai_service.validators import raise_field_validation_error, validate_class_path


class LLMConfig(BaseModel):
    provider: LLMProvider = LLMProvider.OPENAI
    auth_method: AzureAuthMethod = AzureAuthMethod.API_KEY
    model: str | None = None
    azure_endpoint: str | None = None
    api_version: str | None = None
    class_path: str | None = None

    model_config = ConfigDict(extra="allow")

    @model_validator(mode="after")
    def validate_config(self):
        if (
            self.auth_method == AzureAuthMethod.ENTRA_ID
            and self.provider != LLMProvider.AZURE_OPENAI
        ):
            raise_field_validation_error(
                self,
                "auth_method",
                ValueError(
                    "'auth_method = entra_id' is only supported for provider 'azure_openai'."
                ),
            )

        if self.provider == LLMProvider.CUSTOM:
            try:
                validate_class_path(self.class_path)
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
    variant: str | None = None
    vars: dict[str, str] | None = None

    model_config = ConfigDict(extra="allow")


class ProjectPromptConfig(BaseModel):
    file: Path | None = None
    variant: str | None = None
    vars: dict[str, str] | None = None


class AgentConfig(BaseModel):
    enabled: bool
    endpoint_path: str
    class_path: str
    prompt: PromptConfig


class ProjectAgentConfig(BaseModel):
    enabled: bool | None = None
    prompt: ProjectPromptConfig | None = None


class ProjectConfig(BaseModel):
    language: LanguageOption | None = None
    llm_config: LLMConfig | None = None
    agents: dict[str, ProjectAgentConfig] | None = None
