"""Rendering of the context sent to the model.

The requirements endpoint already returns exactly the requirements assigned below
the triggering test theme, so no selection or trimming happens here: every target
is rendered in full, followed by what the theme already contains.
"""

import re
from collections.abc import Callable

from testbench_ai_service.agents.generate_test_idears.model import Requirement, ThemeContext
from testbench_ai_service.models.agent import AgentData
from testbench_ai_service.utils.html_utils import add_html_body_tags, extract_text_from_html_body


class RequirementAgentData(AgentData):
    """Template variables the requirement agent exposes as ``{{ agent.<key> }}``.

    Sections with nothing to show are empty strings rather than missing keys,
    because ``validate_template_and_agent_vars`` matches these names against the
    prompt template at request time.
    """

    requirements: list[str]
    existing_tests: str


#: Requirement attributes rendered on the detail line, in order.
DETAIL_ATTRIBUTES: tuple[tuple[str, Callable[[Requirement], str | None]], ...] = (
    ("version", lambda requirement: requirement.version),
    ("status", lambda requirement: requirement.status),
    ("priority", lambda requirement: requirement.priority),
    ("owner", lambda requirement: requirement.owner),
)

#: A block of test ideas written by an earlier run, as ``template.jinja`` renders it:
#: the bold heading, the pre-wrapped ideas and the disclaimer below them. Matched by
#: structure rather than wording so both languages are recognised, and tolerant of
#: the quoting and whitespace TestBench normalises stored HTML to.
GENERATED_IDEAS_BLOCK = re.compile(
    r"<b>[^<]*</b>\s*<br\s*/?>\s*"
    r"<div style=[\"']white-space:\s*pre-wrap;?[\"']>.*?</div>\s*"
    r"<div style=[\"']padding-top:\s*5px;?[\"']>\s*<div[^>]*>.*?</div>\s*</div>",
    re.DOTALL | re.IGNORECASE,
)

HTML_HEADER = re.compile(r"<head\b[^>]*>.*?</head\s*>", re.DOTALL | re.IGNORECASE)


def strip_html_header(html: str) -> str:
    """Remove every ``<head>`` element, content included, from an HTML string."""
    return HTML_HEADER.sub("", html)


def html_text(html: str) -> str:
    """Return the visible text of an HTML document or fragment, whitespace collapsed.

    A ``<head>`` is left out, so shortening the text keeps the description proper.
    """
    text = extract_text_from_html_body(add_html_body_tags(strip_html_header(html)))
    return " ".join(text.split())


def strip_generated_ideas(html: str) -> str:
    """Remove the test idea blocks earlier runs wrote into a description.

    Fed back to the model, its own earlier output would read as existing coverage
    and be repeated rather than complemented.
    """
    return GENERATED_IDEAS_BLOCK.sub("", html)


def render_requirement(requirement: Requirement, covered_by: list[str] | None = None) -> str:
    """Render a requirement as its identifier and title, its attributes, its description
    and the test case sets already linked to it.

    Attributes that are unset and a description without visible text are omitted
    rather than rendered empty.

    Args:
        requirement: The requirement to render.
        covered_by: Paths of the test case sets linked to the requirement, or
            ``None`` to leave the coverage line out.

    Returns:
        The rendered lines, without a trailing newline.
    """
    lines = [f"- {requirement.external_ref or requirement.key}: {requirement.title}"]
    attributes = [
        f"{label}: {value}"
        for label, value_of in DETAIL_ATTRIBUTES
        if (value := value_of(requirement))
    ]
    if attributes:
        lines.append("  " + " | ".join(attributes))
    description = strip_html_header(requirement.description or "")
    if html_text(description):
        lines.append("  description:")
        lines.extend(f"    {line}" for line in description.strip().splitlines())
    if covered_by is not None:
        lines.append(f"  existing test case sets: {', '.join(covered_by) or 'none'}")
    return "\n".join(lines)


def render_existing_tests(theme_context: ThemeContext) -> str:
    """Render the target theme's own attributes and what is already below it."""
    theme = theme_context.theme
    lines = [f"Test theme: {theme.title}"]
    if theme.path:
        lines.append(f"Path: {' / '.join(theme.path)}")
    if theme.priority:
        lines.append(f"Priority: {theme.priority}")
    if theme.tags:
        lines.append(f"Tags: {', '.join(theme.tags)}")
    lines.extend(f"{name}: {value}" for name, value in theme.udfs.items())
    if description := html_text(strip_generated_ideas(theme.description)):
        lines.append(f"Current description: {description}")
    if review_comment := html_text(theme.review_comment):
        lines.append(f"Review comment: {review_comment}")
    if theme_context.existing_subthemes:
        lines.append("Test themes already below this theme:")
        lines.extend(f"- {path}" for path in theme_context.existing_subthemes)
    if theme_context.existing_test_case_sets:
        lines.append("Test case sets already below this theme:")
        for test_case_set in theme_context.existing_test_case_sets:
            entry = f"- {test_case_set.path}"
            if test_case_set.description_short:
                entry += f": {test_case_set.description_short}"
            lines.append(entry)
    return "\n".join(lines)


def assemble_context(theme_context: ThemeContext) -> RequirementAgentData:
    """Assemble one prompt context covering every requirement of the theme.

    Args:
        theme_context: The target theme, its requirements and what is below it.

    Returns:
        The rendered template variables.
    """
    coverage = theme_context.coverage()
    return {
        "requirements": [
            render_requirement(requirement, coverage[requirement.key])
            for requirement in theme_context.requirements
        ],
        "existing_tests": render_existing_tests(theme_context),
    }
