from pydantic import BaseModel, Field

from testbench_ai_service.models.agent import AgentArgs


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

    #: Upper bound on the requirements sent in one prompt. A theme with more is
    #: skipped before anything is written, instead of risking an oversized prompt.
    max_requirements: int | None = Field(
        default=None,
        gt=0,
        description="Skip themes with more requirements than this. Unset means no limit.",
    )
