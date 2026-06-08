import json
from enum import Enum
from pathlib import Path
from typing import TypedDict

from pydantic import BaseModel, ConfigDict, field_validator

from testbench_ai_service.config import LLMConfig, PromptConfig
from testbench_ai_service.models.language import LanguageOption
from testbench_ai_service.models.testbench import FilteringOptions


class PromptConfigRequest(BaseModel):
    file: Path | None = None
    name: str | None = None
    variant: str | None = None
    vars: dict[str, str] | None = None

    model_config = ConfigDict(extra="allow")


class ElementType(str, Enum):
    BASELINE = "BASELINE"
    CONDITION = "CONDITION"
    DATATYPE = "DATATYPE"
    INTERACTION = "INTERACTION"
    REQUIREMENT = "REQUIREMENT"
    ROOT = "ROOT"
    SUBDIVISION = "SUBDIVISION"
    TESTCASESET = "TESTCASESET"
    TESTTHEME = "TESTTHEME"


class TreeType(str, Enum):
    TESTTHEMES = "TESTTHEMES"
    TESTELEMENTS = "TESTELEMENTS"
    REQUIREMENTS = "REQUIREMENTS"
    DEFECTMANAGEMENT = "DEFECTMANAGEMENT"


class TriggerAgentRequest(BaseModel):
    project_key: str
    tov_key: str | None = None
    cycle_key: str | None = None
    root_uid: str | None = None
    root_key: str | None = None
    element_type: ElementType | None = None
    tree_type: TreeType | None = None
    filtering: FilteringOptions | None = None
    language: LanguageOption | None = None
    prompt_config: PromptConfigRequest | None = None
    llm_config: LLMConfig | None = None

    @field_validator("filtering", mode="before")
    @classmethod
    def parse_filtering_string(cls, v: str | FilteringOptions | None) -> FilteringOptions | None:
        if isinstance(v, str):
            return FilteringOptions.model_validate(json.loads(v))
        return v


class TriggerAgentResponse(BaseModel):
    status: str
    warnings: list[str] | None = None


class ExecutionContext(BaseModel):
    """Holds all resolved data and configuration for a single agent execution."""

    user_key: str
    project_name: str
    project_key: str
    tov_key: str | None = None
    cycle_key: str | None = None
    root_uid: str | None = None
    root_key: str | None = None
    element_type: ElementType | None = None
    tree_type: TreeType | None = None
    filtering: FilteringOptions | None = None
    language: LanguageOption
    llm_config: LLMConfig
    prompt_config: PromptConfig


class AgentResult(BaseModel):
    result: str


class PrecheckResult(BaseModel):
    """Outcome of the precheck phase, including the overall pass/fail status,
    any warnings, and the validated item IDs."""

    passed: bool
    warnings: list[str] = []
    items: list[str] = []


class AgentDetailsResponse(BaseModel):
    """Public representation of an agent, safe to expose via the API."""

    key: str
    enabled: bool
    name: str
    summary: str | None = None
    description: str | None = None


class AgentData(TypedDict, total=False):
    """Agent-generated variables available as ``{{ agent.<key> }}`` in templates."""
