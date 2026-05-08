from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class PromptVariableDefinition(BaseModel):
    """Declares a user-provided variable for a prompt variant."""

    name: str
    description: str | None = None
    value_type: Literal["string", "text", "boolean", "number", "enum"]
    choices: list[str] | None = None
    default_value: Any = None
    required: bool = False

    @model_validator(mode="after")
    def validate_choices(self) -> "PromptVariableDefinition":
        if self.value_type == "enum" and not self.choices:
            raise ValueError("'choices' must be provided when value_type is 'enum'.")
        if self.value_type != "enum" and self.choices is not None:
            raise ValueError("'choices' may only be set when value_type is 'enum'.")
        return self


class MessageTemplate(BaseModel):
    """A message template with Jinja2 content, either inline or from an external file.

    Exactly one of ``text`` (inline Jinja2 template) or ``file`` (path to an
    external template file, e.g. ``.jinja``, ``.j2``, or ``.md``) must be provided.
    """

    role: Literal["system", "user", "assistant"] = "user"
    text: str | None = None
    file: str | None = None

    @model_validator(mode="after")
    def validate_content_source(self) -> "MessageTemplate":
        if self.text is None and self.file is None:
            raise ValueError("Either 'text' or 'file' must be provided for a message template.")
        if self.text is not None and self.file is not None:
            raise ValueError("Only one of 'text' or 'file' may be provided, not both.")
        return self

    def get_content(self, base_path: Path) -> str:
        """Return the template string, loading from *file* if necessary.

        Args:
            base_path: Directory used to resolve relative *file* paths
                       (typically the parent directory of the prompt YAML).
        """
        if self.text is not None:
            return self.text
        assert self.file is not None
        file_path = Path(self.file)
        if not file_path.is_absolute():
            file_path = (base_path / file_path).resolve()
        if not file_path.is_file():
            raise FileNotFoundError(f"Template file not found: {file_path}")
        return file_path.read_text(encoding="utf-8")


class PromptVariant(BaseModel):
    """A variant of a prompt with specific model, variable declarations, and messages."""

    name: str
    description: str | None = None
    model: str | None = None
    vars: dict[str, PromptVariableDefinition] = {}
    messages: list[MessageTemplate]


class PromptDefinition(BaseModel):
    """A prompt definition with multiple variants."""

    name: str
    description: str | None = None
    default_model: str
    default_variant: str
    variants: list[PromptVariant]

    @field_validator("variants")
    @classmethod
    def validate_variants(cls, v: list[PromptVariant]) -> list[PromptVariant]:
        if not v:
            raise ValueError("At least one variant is required")
        return v


class Message(BaseModel):
    """A message in the conversation."""

    role: Literal["system", "user", "assistant"] = "user"
    content: str


class Prompt(BaseModel):
    """A prompt ready to be sent to an LLM."""

    model_name: str = Field(description="The name of the model that should be used for this prompt")
    messages: list[Message] = Field(description="The messages, ready to be sent to an LLM")


class PromptVariantResponse(BaseModel):
    """Public representation of a prompt variant, safe to expose via the API."""

    name: str
    description: str | None = None
    model: str
    vars: dict[str, PromptVariableDefinition]


class PromptDetailsResponse(BaseModel):
    """Response model for the prompt details endpoint."""

    name: str
    file: Path
    default_variant: str
    variants: list[PromptVariantResponse]
