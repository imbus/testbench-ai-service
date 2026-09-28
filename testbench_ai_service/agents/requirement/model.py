from pydantic import BaseModel, ConfigDict, Field, field_validator

from testbench_ai_service.models.agent import AgentArgs
from testbench_ai_service.models.testbench import RequirementAssignment


class ThemeContext(BaseModel):
    """Test-side context gathered for the target test theme."""

    theme_name: str
    #: The theme's description as it stands before generation, so ideas can
    #: complement existing coverage instead of repeating it.
    description: str = ""
    #: Names of the test case sets already below the theme.
    test_case_sets: list[str] = Field(default_factory=list)


class RequirementAgentArgs(AgentArgs):
    """Arguments of the requirement agent, set in its ``args`` config table."""

    max_requirements: int | None = Field(
        default=None,
        gt=0,
        description="Skip themes with more requirements than this. Unset means no limit.",
    )
    rm_service_url: str
    rm_username: str
    rm_password: str

    @field_validator("rm_service_url", mode="after")
    @classmethod
    def ensure_trailing_slash(cls, rm_service_url: str) -> str:
        """Append a trailing slash so paths can be joined onto the URL directly."""
        return rm_service_url if rm_service_url.endswith("/") else f"{rm_service_url}/"


class Requirement(BaseModel):
    key: str
    version: str
    title: str
    description: str | None
    status: str | None
    priority: str | None
    owner: str | None
    documents: list[str]
    external_ref: str | None


class ExtendedRequirementKey(BaseModel):
    id: str
    version: str


class ExtendedRequirement(BaseModel):
    """A requirement as returned by the RM service's ``extended-requirement`` endpoint."""

    model_config = ConfigDict(populate_by_name=True)
    name: str
    extendedId: str = Field(alias="extendedID")
    key: ExtendedRequirementKey
    owner: str
    status: str
    priority: str
    requirement: bool
    description: str | None
    documents: list[str] | None
    baseline: str | None

    @classmethod
    def from_assignment(cls, assignment: RequirementAssignment) -> "ExtendedRequirement":
        """Build a fallback from the TOV's requirement data alone, without RM details."""
        return cls(
            name=assignment.name,
            extendedId=assignment.extendedId,
            key=ExtendedRequirementKey(id=assignment.id, version=assignment.version),
            owner=assignment.owner,
            status=assignment.status,
            priority=assignment.priority,
            requirement=True,
            description=None,
            documents=None,
            baseline=None,
        )


class ExistingTestCaseSet(BaseModel):
    key: str
    title: str
    description_short: str
    requirement_keys: list[str]
    ai_generated: bool


class Theme(BaseModel):
    key: str
    title: str
    description: str
    path: list[str]


class PromptContext(BaseModel):
    theme: Theme
    requirements: list[Requirement]
    existing_subthemes: list[str]
    existing_test_case_sets: list[ExistingTestCaseSet]
    context_requirement_titles: list[str]  # Eltern, nur Orientierung

    def coverage(self) -> dict[str, list[str]]: ...
