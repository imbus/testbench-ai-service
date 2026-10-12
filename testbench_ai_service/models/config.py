from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from testbench_ai_service.llm.base import AzureAuthMethod, LLMProvider, RoutingFamily
from testbench_ai_service.models.language import LanguageOption
from testbench_ai_service.validators import raise_field_validation_error, validate_class_path

#: Which request shapes each provider's client can actually produce.
#: AZURE_OPENAI shares OpenAI's two branches (it dispatches on the canonical
#: name after deployment_mapping); CUSTOM implements its own dispatch, so
#: "fallback" is the only honest answer for it.
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

        # Imported here rather than at module scope: llm.routing imports both
        # client modules (and their SDKs), and models/config.py is imported by
        # nearly everything. Keeping it function-local keeps that weight out of
        # the common import path. Same pattern as 4b's template_refs import.
        from testbench_ai_service.llm.routing import builtin_routing  # noqa: PLC0415

        for name, entry in self.extra_models.items():
            allowed = ALLOWED_ROUTING[entry.provider]
            if entry.routing not in allowed:
                # Full loc tuple, not the bare field name: the console renders a
                # ConfigIssue against the offending ROW (design 5.3), which needs
                # the model name and the field in the path. Same shape as
                # config.py:336's ("projects", ..., "prompt", "file").
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
