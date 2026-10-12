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
    """A variant of a prompt with specific model, variable declarations, and messages.

    A variant either sends one prompt (``messages``) or drives an agent that asks
    the model several times (``steps``: one message list per named step). Using
    both at once is rejected, so it is always clear what an agent renders.
    """

    name: str
    description: str | None = None
    model: str | None = None
    vars: dict[str, PromptVariableDefinition] = {}
    messages: list[MessageTemplate]
    steps: dict[str, list[MessageTemplate]] = {}

    @model_validator(mode="after")
    def validate_messages_or_steps(self) -> "PromptVariant":
        if self.messages and self.steps:
            raise ValueError("A variant uses either 'messages' or 'steps', not both.")
        empty = sorted(name for name, templates in self.steps.items() if not templates)
        if empty:
            raise ValueError(f"Steps without messages: {', '.join(empty)}")
        return self

    def templates_for(self, step: str | None) -> list[MessageTemplate]:
        """The message templates of *step*, or the plain ``messages`` without one.

        Raises:
            ValueError: The variant has no such step.
        """
        if step is None:
            return self.messages
        try:
            return self.steps[step]
        except KeyError:
            raise ValueError(f"Step '{step}' not found in variant '{self.name}'.") from None


class PromptDefinition(BaseModel):
    """A prompt definition with multiple variants."""

    name: str
    summary: str | None = None
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
    summary: str | None = None
    description: str | None = None
    file: Path
    default_variant: str
    variants: list[PromptVariantResponse]
