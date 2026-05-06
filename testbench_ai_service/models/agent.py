from pathlib import Path
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

from testbench_ai_service.config import LLMConfig, PromptConfig
from testbench_ai_service.models.language import LanguageOption
from testbench_ai_service.models.testbench import FilteringOptions

T = TypeVar("T")


class PromptConfigRequest(BaseModel):
    file: Path | None = None
    name: str | None = None
    variant: str | None = None
    placeholder_data: dict[str, str] | None = None

    model_config = ConfigDict(extra="allow")


class TriggerAgentRequest(BaseModel):
    project_key: str
    tov_key: str
    cycle_key: str | None = None
    root_uid: str | None = None
    tree_root_key: str
    element_type: str
    tree_type: str
    filtering: FilteringOptions | None = None
    language: LanguageOption | None = None
    prompt_config: PromptConfigRequest | None = None
    llm_config: LLMConfig | None = None


class TriggerAgentResponse(BaseModel):
    status: str
    warnings: list[str] | None = None


class ExecutionContext(BaseModel):
    """Holds all resolved data and configuration for a single agent execution."""

    user_key: str
    project_name: str
    project_key: str
    tov_key: str
    cycle_key: str | None = None
    root_uid: str | None = None
    tree_root_key: str | None = None
    element_type: str | None = None
    tree_type: str | None = None
    filtering: FilteringOptions | None = None
    language: LanguageOption
    llm_config: LLMConfig
    prompt_config: PromptConfig


class AgentResult(BaseModel):
    result: str


class PrecheckResult(BaseModel, Generic[T]):
    """Outcome of the precheck phase, including items ready for execution."""

    passed: bool
    warnings: list[str] = []


class AgentDetailsResponse(BaseModel):
    """Public representation of an agent, safe to expose via the API."""

    key: str
    enabled: bool
    summary: str | None = None
    description: str | None = None
