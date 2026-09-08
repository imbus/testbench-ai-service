"""Tiered, budget-trimmed assembly of the context sent to the model.

A requirement carries no prose: its name is a ten-word title and its UDFs a handful
of characters. What context exists is therefore structural, and this module spends a
token budget on it in priority order.

Tiers 1 to 3 -- the target, its ancestors and subtree, its siblings -- are the
structural core and are always included; they are small by construction, bounded by
the depth and branching of one baseline subtree rather than by baseline size. Tiers
4 to 6 are trimmed, and because they are assembled in order, a large tier 6 can
never crowd out the theme tiers before it.

Trimming happens at entry granularity. A tier that cannot fit even its first entry
renders as an empty string rather than a fragment, so the prompt never shows the
model half a requirement.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from math import ceil

from testbench_ai_service.agents.requirement.model import (
    Baseline,
    Requirement,
    ThemeContext,
)
from testbench_ai_service.agents.requirement.ranking import Ranker
from testbench_ai_service.agents.requirement.tree import (
    ancestors,
    render_detail,
    render_line,
    siblings,
    subtree,
)
from testbench_ai_service.agents.requirement.utils import iter_requirements
from testbench_ai_service.log import logger
from testbench_ai_service.models.agent import AgentData

#: Characters per token, used to size sections without a tokeniser dependency.
#:
#: Four is the usual English approximation and errs slightly high on identifier-dense
#: text like ``ER_WHY299``. Sizing is a budget guard, not an accounting record, so an
#: approximation that never under-counts badly is enough.
CHARS_PER_TOKEN = 4


class RequirementAgentData(AgentData):
    """Template variables the requirement agent exposes as ``{{ agent.<key> }}``.

    Every field is a rendered string so that selection stays in Python and
    presentation stays in the Jinja template. Sections with nothing to show are
    empty strings rather than missing keys, because
    ``validate_template_and_agent_vars`` matches these names against the prompt
    template at request time.
    """

    requirement: str
    requirement_path: str
    requirement_subtree: str
    requirement_siblings: str
    existing_tests: str
    related_tests: str
    related_requirements: str
    requirement_obj: Requirement


@dataclass(frozen=True)
class TokenBudget:
    """Token allowances for the trimmable tiers.

    Args:
        total: Ceiling for the whole assembled context.
        existing_tests: Cap for the target theme's own description and test case
            sets (tier 4).
        related_tests: Cap for tests linked to nearby requirements (tier 5).
        related_requirements: Cap for the ranked related requirements (tier 6).
    """

    total: int = 8000
    existing_tests: int = 1200
    related_tests: int = 1500
    related_requirements: int = 2500


def estimate_tokens(text: str) -> int:
    """Estimate the token cost of a rendered section.

    Args:
        text: The rendered text.

    Returns:
        An approximate token count, rounded up. Zero for empty text.
    """
    return ceil(len(text) / CHARS_PER_TOKEN)


def _fit_entries(entries: Sequence[str], allowance: int) -> str:
    """Join as many whole entries as the allowance permits.

    Args:
        entries: Rendered entries, most valuable first.
        allowance: Tokens available for this tier.

    Returns:
        The joined entries that fit, or an empty string if not even the first does.
    """
    kept: list[str] = []
    spent = 0

    for entry in entries:
        cost = estimate_tokens(entry) + 1
        if spent + cost > allowance:
            break
        kept.append(entry)
        spent += cost

    return "\n".join(kept)


def _render_existing_tests(theme_context: ThemeContext | None) -> str:
    """Render the target theme's own description and test case sets (tier 4)."""
    if theme_context is None:
        return ""

    lines = [f"Test theme: {theme_context.theme_name}"]
    if theme_context.description.strip():
        lines.append(f"Current description: {theme_context.description}")
    if theme_context.test_case_sets:
        lines.append("Test case sets already below this theme:")
        lines.extend(f"- {name}" for name in theme_context.test_case_sets)

    return "\n".join(lines)


def _render_related_tests(theme_context: ThemeContext | None) -> str:
    """Render tests linked to nearby requirements (tier 5)."""
    if theme_context is None or not theme_context.related_tests:
        return ""

    lines: list[str] = []
    for extended_id, names in theme_context.related_tests.items():
        lines.append(f"- {extended_id}:")
        lines.extend(f"  - {name}" for name in names)

    return "\n".join(lines)


def _candidates(baseline: Baseline, target: Requirement) -> list[Requirement]:
    """Return every requirement in the baseline other than the target."""
    return [
        node
        for node in iter_requirements(baseline.children)
        if node.key.serial != target.key.serial
    ]


def _render_lines(nodes: Iterable[Requirement]) -> str:
    """Render nodes as one detail block per node, in the order given."""
    return "\n".join(render_detail(node) for node in nodes)


async def assemble_context(
    *,
    baseline: Baseline,
    target: Requirement,
    theme_context: ThemeContext | None,
    ranker: Ranker,
    budget: TokenBudget,
) -> RequirementAgentData:
    """Assemble the prompt context for one requirement.

    Args:
        baseline: The loaded baseline holding the requirement tree.
        target: The resolved target requirement.
        theme_context: Test-side context for the target theme, or ``None`` when none
            could be gathered.
        ranker: Strategy ordering the tier-6 candidates.
        budget: Token allowances for the trimmable tiers.

    Returns:
        The rendered template variables, with empty strings for sections that have
        nothing to show or did not fit.
    """
    requirement = render_detail(target)
    requirement_path = "\n".join(
        render_line(node, depth) for depth, node in enumerate(ancestors(baseline.children, target))
    )
    requirement_subtree = "\n".join(
        render_detail(node, depth - 1) for depth, node in subtree(target)
    )
    requirement_siblings = _render_lines(siblings(baseline.children, target))

    core = [requirement, requirement_path, requirement_subtree, requirement_siblings]
    spent = sum(estimate_tokens(section) for section in core)

    existing_tests = _fit_entries(
        [_render_existing_tests(theme_context)],
        min(budget.existing_tests, max(budget.total - spent, 0)),
    )
    spent += estimate_tokens(existing_tests)

    related_tests = _fit_entries(
        [_render_related_tests(theme_context)],
        min(budget.related_tests, max(budget.total - spent, 0)),
    )
    spent += estimate_tokens(related_tests)

    ordered = await ranker.order(target, _candidates(baseline, target))
    related_requirements = _fit_entries(
        [render_line(node) for node in ordered],
        min(budget.related_requirements, max(budget.total - spent, 0)),
    )
    spent += estimate_tokens(related_requirements)

    logger.debug(
        "Assembled context for requirement '%s': ~%d token(s) of %d, "
        "%d ranked candidate(s) available, %d included",
        target.extendedID,
        spent,
        budget.total,
        len(ordered),
        len(related_requirements.splitlines()) if related_requirements else 0,
    )

    return {
        "requirement": requirement,
        "requirement_path": requirement_path,
        "requirement_subtree": requirement_subtree,
        "requirement_siblings": requirement_siblings,
        "existing_tests": existing_tests,
        "related_tests": related_tests,
        "related_requirements": related_requirements,
        "requirement_obj": target,
    }
