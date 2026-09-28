"""Rendering of the context sent to the model.

The requirements endpoint already returns exactly the requirements assigned below
the triggering test theme, so no selection or trimming happens here: every target
is rendered in full, followed by what the theme already contains.
"""

from collections.abc import Callable, Sequence

from testbench_ai_service.agents.requirement.model import ExtendedRequirement, ThemeContext
from testbench_ai_service.models.agent import AgentData
from testbench_ai_service.utils.html_utils import has_visible_text


class RequirementAgentData(AgentData):
    """Template variables the requirement agent exposes as ``{{ agent.<key> }}``.

    Sections with nothing to show are empty strings rather than missing keys,
    because ``validate_template_and_agent_vars`` matches these names against the
    prompt template at request time.
    """

    requirements: list[str]
    existing_tests: str


#: Requirement attributes rendered on the detail line, in order.
DETAIL_ATTRIBUTES: tuple[tuple[str, Callable[[ExtendedRequirement], str | None]], ...] = (
    ("version", lambda requirement: requirement.key.version),
    ("status", lambda requirement: requirement.status),
    ("priority", lambda requirement: requirement.priority),
    ("owner", lambda requirement: requirement.owner),
)


def render_requirement(requirement: ExtendedRequirement) -> str:
    """Render a requirement as its identifier and title, its attributes and its description.

    Attributes that are unset and a description without visible text are omitted
    rather than rendered empty.

    Args:
        requirement: The requirement to render.

    Returns:
        The rendered lines, without a trailing newline.
    """
    lines = [f"- {requirement.extendedId}: {requirement.name}"]
    attributes = [
        f"{label}: {value}"
        for label, value_of in DETAIL_ATTRIBUTES
        if (value := value_of(requirement))
    ]
    if attributes:
        lines.append("  " + " | ".join(attributes))
    if requirement.description and has_visible_text(requirement.description):
        lines.append("  description:")
        lines.extend(f"    {line}" for line in requirement.description.strip().splitlines())
    return "\n".join(lines)


def render_existing_tests(theme_context: ThemeContext) -> str:
    """Render the target theme's own description and test case sets."""
    lines = [f"Test theme: {theme_context.theme_name}"]
    if theme_context.description.strip():
        lines.append(f"Current description: {theme_context.description}")
    if theme_context.test_case_sets:
        lines.append("Test case sets already below this theme:")
        lines.extend(f"- {name}" for name in theme_context.test_case_sets)
    return "\n".join(lines)


def assemble_context(
    *,
    targets: Sequence[ExtendedRequirement],
    theme_context: ThemeContext,
) -> RequirementAgentData:
    """Assemble one prompt context covering every target requirement.

    Args:
        targets: The requirements to generate ideas for, in the order they are shown.
        theme_context: Test-side context for the target theme.

    Returns:
        The rendered template variables.
    """
    return {
        "requirements": [render_requirement(target) for target in targets],
        "existing_tests": render_existing_tests(theme_context),
    }
