from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class Block(BaseModel):
    """A content block within a prompt variant."""

    role: Literal["system", "user", "assistant"] = "user"
    text: str


class PromptVariant(BaseModel):
    """A variant of a prompt with specific model and blocks."""

    name: str
    description: str | None = None
    model: str
    blocks: list[Block]


class PromptDefinition(BaseModel):
    """A prompt definition with multiple variants."""

    name: str
    description: str | None = None
    default_variant: str | None = None
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
    placeholders: list[str]
    user_placeholders: list[str]


class PromptDetailsResponse(BaseModel):
    """Response model for the prompt details endpoint."""

    name: str
    file: Path
    generated_placeholders: list[str]
    default_variant: str | None
    variants: list[PromptVariantResponse]
