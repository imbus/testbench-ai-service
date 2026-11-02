from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from testbench_ai_service.llm.base import AzureAuthMethod, LLMProvider, RoutingFamily
from testbench_ai_service.models.language import LanguageOption
from testbench_ai_service.validators import raise_field_validation_error, validate_class_path


ALLOWED_ROUTING: dict[LLMProvider, frozenset[RoutingFamily]] = {
    LLMProvider.OPENAI: frozenset(
        {RoutingFamily.CHAT, RoutingFamily.REASONING, RoutingFamily.FALLBACK}
    ),
    LLMProvider.AZURE_OPENAI: frozenset(
        {RoutingFamily.CHAT, RoutingFamily.REASONING, RoutingFamily.FALLBACK}
    ),
    LLMProvider.ANTHROPIC: frozenset(
        {RoutingFamily.ADAPTIVE, RoutingFamily.BUDGET, RoutingFamily.FALLBACK}
    ),
    LLMProvider.CUSTOM: frozenset({RoutingFamily.FALLBACK}),
}


class ExtraModel(BaseModel):
    """One operator-supplied catalogue entry.

    ``routing`` is not decoration: it is the branch the client will take for
    this model. Without it a newly added model falls through to
    ``_query_fallback_model`` -- no thinking, no effort, max_tokens 4096 --
    which is the opposite of what an operator adding a new flagship wants
    (design D10).
    """

    provider: LLMProvider
    routing: RoutingFamily


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
    extra_models: dict[str, ExtraModel] = Field(
        default_factory=dict,
        description=(
            "Models to offer in the console beyond those the clients already route, "
            "keyed by model name. Each entry names its provider and the request shape "
            "the client should use for it."
        ),
    )
    agent_models: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "The model one agent runs on, keyed by agent key. Takes precedence over "
            "'model'; a project or request table overrides it agent by agent."
        ),
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

        from testbench_ai_service.llm.routing import builtin_routing  # noqa: PLC0415

        for name, entry in self.extra_models.items():
            allowed = ALLOWED_ROUTING[entry.provider]
            if entry.routing not in allowed:
                raise_field_validation_error(
                    self,
                    ("extra_models", name, "routing"),
                    ValueError(
                        f"'{name}': routing '{entry.routing}' is not available for provider "
                        f"'{entry.provider}'. Allowed: "
                        f"{', '.join(sorted(family.value for family in allowed))}."
                    ),
                )
            if builtin_routing(name) is not None:
                # The whole entry is the problem here, not one of its fields.
                raise_field_validation_error(
                    self,
                    ("extra_models", name),
                    ValueError(
                        f"'{name}' is already routed by its client and cannot be redefined "
                        "here. Remove the entry; the model is offered automatically."
                    ),
                )
        return self


def resolved_extra_models(config: LLMConfig) -> dict[str, ExtraModel]:
    """``config.extra_models`` as ``ExtraModel`` objects, whatever the merge left.

    ``get_llm_config`` merges a project's block with
    ``model_copy(update=project.llm_config.model_dump(exclude_unset=True))``,
    and ``model_copy`` skips validation -- so after a project override the
    entries are the plain dicts ``model_dump`` produced, not ``ExtraModel``
    instances. Every reader that does ``entry.provider`` would then raise
    ``AttributeError`` on exactly the per-project catalogue design 5.3
    promises. Coercing here keeps that knowledge in one place instead of two.

    A malformed entry is dropped rather than raised on: both callers are on a
    path where one bad row must not take out the whole catalogue or every
    client constructor, and ``validate_config_dict`` already refuses such a
    row, with a field-addressed issue, before it can be written.
    """
    resolved: dict[str, ExtraModel] = {}
    for name, entry in (config.extra_models or {}).items():
        if isinstance(entry, ExtraModel):
            resolved[name] = entry
            continue
        try:
            resolved[name] = ExtraModel.model_validate(entry)
        except ValidationError:
            continue
    return resolved


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


class JobsConfig(BaseModel):
    retention_days: int = Field(
        default=90, gt=0, description="Delete jobs older than this many days at startup."
    )


class AgentConfig(BaseModel):
    enabled: bool
    endpoint_path: str
    class_path: str
    prompt: PromptConfig
    args: dict[str, Any] = Field(default_factory=dict)


class ProjectAgentConfig(BaseModel):
    enabled: bool | None = None
    prompt: ProjectPromptConfig | None = None
    args: dict[str, Any] | None = None


def merge_agent_args(
    global_args: dict[str, Any], project_args: dict[str, Any] | None
) -> dict[str, Any]:
    """
    Merge project-specific agent args over the global ones, key by key.

    Args:
        global_args: The ``args`` table of the global agent config.
        project_args: The ``args`` table of a project override, if any.

    Returns:
        A new dict with the project keys taking precedence.
    """
    return {**global_args, **(project_args or {})}


class ProjectConfig(BaseModel):
    language: LanguageOption | None = None
    llm_config: LLMConfig | None = None
    agents: dict[str, ProjectAgentConfig] | None = None
