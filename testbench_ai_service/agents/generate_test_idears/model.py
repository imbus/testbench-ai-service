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
    max_ideas_per_theme: int | None = Field(
        default=None,
        gt=0,
        description="Keep at most this many test ideas per theme. Unset means no limit.",
    )

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


class TestIdea(BaseModel):
    """One test idea as the model returns it."""

    title: str
    description: str = ""
    #: Identifiers of the requirements the idea covers, for traceability.
    covered_requirements: list[str] = Field(default_factory=list)

    @field_validator("title", "description", mode="after")
    @classmethod
    def strip_text(cls, text: str) -> str:
        return text.strip()

    @field_validator("covered_requirements", mode="after")
    @classmethod
    def strip_keys(cls, keys: list[str]) -> list[str]:
        return [key.strip() for key in keys if key.strip()]


class IdeaGroup(BaseModel):
    """Test ideas under a common subtheme, or directly under the theme."""

    #: Name of the subtheme, or ``None`` for ideas directly under the theme.
    theme_name: str | None = None
    ideas: list[TestIdea] = Field(default_factory=list)

    @field_validator("theme_name", mode="after")
    @classmethod
    def blank_name_to_none(cls, theme_name: str | None) -> str | None:
        if theme_name is None or not theme_name.strip():
            return None
        return theme_name.strip()


class TestIdeaResult(BaseModel):
    """The model's whole answer for a theme; an empty ``groups`` list is valid."""

    groups: list[IdeaGroup] = Field(default_factory=list)

    @property
    def ideas(self) -> list[TestIdea]:
        """All ideas, in the order they appear."""
        return [idea for group in self.groups for idea in group.ideas]


#: Fewest ideas a subtheme must hold; a smaller group is dissolved into the theme.
MIN_IDEAS_PER_GROUP = 2


def _normalized(name: str) -> str:
    """Casefold and collapse whitespace, for comparing names."""
    return " ".join(name.split()).casefold()


def apply_guardrails(
    result: TestIdeaResult,
    *,
    allowed_requirements: set[str],
    existing_theme_names: set[str],
    max_ideas: int | None = None,
) -> TestIdeaResult:
    """Normalise the model's answer deterministically, whatever the prompt asked for.

    The model groups freely; this enforces the rules the result must satisfy:

    - ``covered_requirements`` keeps only the theme's own requirements, deduplicated.
    - Ideas without a title and ideas repeating an earlier title are dropped.
    - Groups with the same name are merged; at most ``max_ideas`` ideas are kept.
    - Groups left with fewer than :data:`MIN_IDEAS_PER_GROUP` ideas are dissolved,
      their ideas moving directly under the theme.
    - A subtheme name that collides with an existing one gets a numeric suffix.

    Nesting is limited to one level by the schema itself. Ungrouped ideas come
    last, in a single group without a name.

    Args:
        result: The validated answer of the model.
        allowed_requirements: Identifiers of the requirements linked to the theme.
        existing_theme_names: Names of the test themes already below the theme.
        max_ideas: Upper bound on the ideas kept, or ``None`` for no limit.

    Returns:
        The normalised result; the input is left unchanged.
    """
    seen_titles: set[str] = set()
    grouped: dict[str | None, list[TestIdea]] = {}
    names: dict[str, str] = {}
    kept = 0
    for group in result.groups:
        key = None
        if group.theme_name is not None:
            key = _normalized(group.theme_name)
            names.setdefault(key, group.theme_name)
        for idea in group.ideas:
            title = _normalized(idea.title)
            if not title or title in seen_titles:
                continue
            if max_ideas is not None and kept >= max_ideas:
                break
            seen_titles.add(title)
            kept += 1
            covered = [ref for ref in idea.covered_requirements if ref in allowed_requirements]
            grouped.setdefault(key, []).append(
                idea.model_copy(update={"covered_requirements": list(dict.fromkeys(covered))})
            )

    ungrouped = grouped.pop(None, [])
    taken = {_normalized(name) for name in existing_theme_names}
    groups: list[IdeaGroup] = []
    for key, ideas in grouped.items():
        if key is None or len(ideas) < MIN_IDEAS_PER_GROUP:
            ungrouped.extend(ideas)
            continue
        name = _unique_name(names[key], taken)
        taken.add(_normalized(name))
        groups.append(IdeaGroup(theme_name=name, ideas=ideas))
    if ungrouped:
        groups.append(IdeaGroup(theme_name=None, ideas=ungrouped))
    return TestIdeaResult(groups=groups)


def _unique_name(name: str, taken: set[str]) -> str:
    """Return ``name``, or ``name (2)``, ``name (3)``, ... if it is already taken."""
    candidate, suffix = name, 2
    while _normalized(candidate) in taken:
        candidate, suffix = f"{name} ({suffix})", suffix + 1
    return candidate
