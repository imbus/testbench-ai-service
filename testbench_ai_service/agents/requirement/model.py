from pydantic import BaseModel, ConfigDict, Field


class Key(BaseModel):
    """A legacy TestBench entity key."""

    serial: str


class RequirementUdf(BaseModel):
    """A single user-defined field of a requirement.

    The legacy requirement UDFs are not the same shape as
    :class:`testbench_ai_service.models.testbench.UserDefinedField`: they carry no
    key, and their ``type`` uses RE repository type names such as
    ``"ShortTextfield"`` rather than the ``UDFType`` enum values.
    """

    name: str
    type: str
    value: str


class RequirementUdfs(BaseModel):
    """One entry of the ``baselines/{serial}/udfs`` payload.

    ``key`` is the *requirement* key, matching ``Requirement.requirementKey`` --
    not ``Requirement.key``, which is the baseline-scoped node key.
    """

    key: Key
    value: list[RequirementUdf] = Field(default_factory=list)


class Requirement(BaseModel):
    """A requirement node in a baseline's requirement tree.

    ``key`` identifies the node inside the baseline, while ``requirementKey``
    identifies the underlying requirement and is what UDFs are keyed by.
    """

    key: Key
    requirementKey: Key
    baselineKey: Key
    id: str
    extendedID: str
    name: str
    version: str | None = None
    status: str | None = None
    owner: str | None = None
    priority: str | None = None
    isFolder: bool = False
    children: list["Requirement"] = Field(default_factory=list)
    udfs: list[RequirementUdf] = Field(default_factory=list)


class Baseline(BaseModel):
    """A requirement baseline together with its loaded requirement tree."""

    key: Key
    name: str
    type: str | None = None
    repository: str | None = None
    reqProjectName: str | None = None
    reProjectKey: Key | None = None
    lastUpdate: str | None = None
    children: list[Requirement] = Field(default_factory=list)
    areRequirementsLoaded: bool = False
    loadingError: str | None = None


class LoaderJobError(BaseModel):
    """The failure branch of a loader job result."""

    message: str | None = None
    details: str | None = None
    trace: str | None = None
    cause: str | None = None


class LoaderJobResult(BaseModel):
    """The ``Either`` result of a loader job: ``Right`` on success, ``Left`` on failure."""

    model_config = ConfigDict(populate_by_name=True)

    right: Baseline | None = Field(default=None, alias="Right")
    left: LoaderJobError | None = Field(default=None, alias="Left")


class LoaderJobCompletion(BaseModel):
    """Completion envelope of a loader job; absent while the job is still running."""

    time: str | None = None
    result: LoaderJobResult


class RequirementsLoaderJob(BaseModel):
    """The ``requirementsLoaderJob/{jobId}`` payload."""

    id: str
    start: str | None = None
    completion: LoaderJobCompletion | None = None


class ThemeContext(BaseModel):
    """Test-side context gathered for a target test theme.

    Populated by :mod:`testbench_ai_service.agents.requirement.linking`, consumed by
    the context assembler as tiers 4 and 5. Kept separate from the requirement models
    because it describes the test structure tree, not the requirement tree.
    """

    theme_name: str
    #: The theme's description as it stands before generation, so ideas can
    #: complement existing coverage instead of repeating it.
    description: str = ""
    #: Names of the test case sets already below the theme.
    test_case_sets: list[str] = Field(default_factory=list)
    #: Test case set names per nearby requirement, keyed by ``extendedID``. Only
    #: requirements of the structural core appear here, which bounds the lookup.
    related_tests: dict[str, list[str]] = Field(default_factory=dict)
