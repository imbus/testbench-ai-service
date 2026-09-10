from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
    timeout: float | None = Field(
        default=None,
        gt=0,
        description="Seconds to wait for an LLM response before giving up. Unset uses the provider SDK's own default.",
    )
    max_retries: int | None = Field(
        default=None,
        ge=0,
        description="How often the provider SDK retries a failed request. Unset uses the SDK's own default.",
    )

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


# Prompt variables carry the value types PromptVariableDefinition declares
# ('number' and 'boolean' as well as the string kinds), so the config that
# supplies them has to be able to hold them. Order matters for pydantic's
# smart union only in that every member is a distinct scalar type; bool is
# listed before int deliberately, since bool is a subclass of int.
PromptVarValue = str | bool | int | float


class PromptConfig(BaseModel):
    file: Path
    variant: str | None = None
    vars: dict[str, PromptVarValue] | None = None

    model_config = ConfigDict(extra="allow")


class ProjectPromptConfig(BaseModel):
    file: Path | None = None
    variant: str | None = None
    vars: dict[str, PromptVarValue] | None = None


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
