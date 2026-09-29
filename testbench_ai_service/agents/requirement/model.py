from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from testbench_ai_service.models.agent import AgentArgs
from testbench_ai_service.models.testbench import RequirementAssignment


class RequirementAgentArgs(AgentArgs):
    """Arguments of the requirement agent, set in its ``args`` config table."""

    max_requirements: int | None = Field(
        default=None,
        gt=0,
        description="Skip themes with more requirements than this. Unset means no limit.",
    )
    rm_service_url: str | None = Field(
        default=None,
        description="RM service to fetch requirement details from. Unset means TOV data only.",
    )
    rm_username: str | None = None
    rm_password: str | None = None

    @field_validator("rm_service_url", mode="after")
    @classmethod
    def ensure_trailing_slash(cls, rm_service_url: str | None) -> str | None:
        """Append a trailing slash so paths can be joined onto the URL directly."""
        if rm_service_url is None or rm_service_url.endswith("/"):
            return rm_service_url
        return f"{rm_service_url}/"

    @model_validator(mode="after")
    def require_rm_credentials(self) -> "RequirementAgentArgs":
        """Reject an RM service URL configured without the credentials to call it."""
        if self.rm_service_url is not None and (
            self.rm_username is None or self.rm_password is None
        ):
            raise ValueError("rm_service_url requires rm_username and rm_password")
        return self


class Requirement(BaseModel):
    """A requirement as the model sees it: its TOV assignment merged with its RM details."""

    #: TestBench key, which test case sets reference the requirement by.
    key: str
    version: str
    title: str
    description: str | None
    status: str | None
    priority: str | None
    owner: str | None
    documents: list[str]
    external_ref: str | None

    @classmethod
    def from_details(
        cls, assignment: RequirementAssignment, extended: "ExtendedRequirement"
    ) -> "Requirement":
        """Merge a requirement's TOV assignment with its extended data."""
        return cls(
            key=assignment.key,
            version=extended.key.version,
            title=extended.name,
            description=extended.description,
            status=extended.status or None,
            priority=extended.priority or None,
            owner=extended.owner or None,
            documents=extended.documents or [],
            external_ref=extended.extendedId or None,
        )


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
    """A test case set already somewhere below the target theme."""

    key: str
    title: str
    path: str
    description_short: str
    requirement_keys: list[str]


class Theme(BaseModel):
    """The target test theme."""

    key: str
    title: str
    description: str = ""
    review_comment: str = ""
    path: list[str] = Field(default_factory=list)
    priority: str | None = None
    tags: list[str] = Field(default_factory=list)
    udfs: dict[str, str] = Field(default_factory=dict)


class ThemeContext(BaseModel):
    """Everything the model is told about the target theme and its requirements."""

    theme: Theme
    requirements: list[Requirement] = Field(default_factory=list)
    existing_subthemes: list[str] = Field(default_factory=list)
    existing_test_case_sets: list[ExistingTestCaseSet] = Field(default_factory=list)
    context_requirement_titles: list[str] = Field(default_factory=list)

    def coverage(self) -> dict[str, list[str]]:
        """Map each requirement's key to the paths of the test case sets linked to it.

        Every requirement of the theme has an entry, an empty list when no set
        covers it. Links to requirements outside the theme are left out.
        """
        coverage: dict[str, list[str]] = {requirement.key: [] for requirement in self.requirements}
        for test_case_set in self.existing_test_case_sets:
            for key in test_case_set.requirement_keys:
                if key in coverage:
                    coverage[key].append(test_case_set.path)
        return coverage
