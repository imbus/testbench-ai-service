from pydantic import BaseModel, Field


class ThemeContext(BaseModel):
    """Test-side context gathered for the target test theme."""

    theme_name: str
    #: The theme's description as it stands before generation, so ideas can
    #: complement existing coverage instead of repeating it.
    description: str = ""
    #: Names of the test case sets already below the theme.
    test_case_sets: list[str] = Field(default_factory=list)
