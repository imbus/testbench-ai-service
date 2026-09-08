"""Pure navigation and rendering helpers for a requirement tree.

Nothing here performs I/O: every function takes an already-loaded tree, which
keeps context assembly testable against a fixture baseline.

A trigger's ``root_uid`` is resolved to a node exactly once, by
:func:`find_requirement`; every other function takes that resolved node. Nodes are
identified by ``key.serial``, the baseline-scoped node key, which is unique within
a baseline -- unlike ``requirementKey.serial``, which a requirement shares across
the baselines it appears in.
"""

from collections.abc import Callable, Iterable

from testbench_ai_service.agents.requirement.model import Requirement
from testbench_ai_service.agents.requirement.utils import iter_requirements
from testbench_ai_service.log import logger

#: How a ``root_uid`` is matched against a requirement, in order of precedence.
#:
#: The trigger request carries a ``root_uid`` that is a ``uniqueID`` for the test
#: structure tree, but requirements expose neither -- they have ``extendedID``,
#: ``id``, and two unrelated key spaces. Which one TestBench sends for a
#: requirement is not yet confirmed, so every candidate is tried and the field that
#: matched is logged.
RESOLUTION_FIELDS: tuple[tuple[str, Callable[[Requirement], str]], ...] = (
    ("extendedID", lambda requirement: requirement.extendedID),
    ("id", lambda requirement: requirement.id),
    ("requirementKey.serial", lambda requirement: requirement.requirementKey.serial),
    ("key.serial", lambda requirement: requirement.key.serial),
)


def find_requirement(requirements: Iterable[Requirement], uid: str) -> Requirement | None:
    """Locate the requirement a trigger's ``root_uid`` refers to.

    Each field in :data:`RESOLUTION_FIELDS` is tried across the whole tree before
    the next one, so a match on a higher-precedence field always wins -- even when
    the matching node sits deeper than a lower-precedence match elsewhere.

    Args:
        requirements: The tree's root requirements.
        uid: The ``root_uid`` from the execution context.

    Returns:
        The matched requirement, or ``None`` if no field of any node matches.
    """
    nodes = list(iter_requirements(requirements))

    for field, value_of in RESOLUTION_FIELDS:
        for node in nodes:
            if value_of(node) == uid:
                logger.debug(
                    "Resolved root_uid '%s' to requirement '%s' via %s",
                    uid,
                    node.extendedID,
                    field,
                )
                return node

    logger.debug("root_uid '%s' matched none of %d requirement(s)", uid, len(nodes))
    return None


def _path_to(
    requirements: Iterable[Requirement],
    target: Requirement,
) -> list[Requirement] | None:
    """Return the node chain from ``requirements`` down to ``target``, inclusive.

    Args:
        requirements: The nodes to search, each with their children.
        target: The requirement to locate, identified by ``key.serial``.

    Returns:
        The chain ending in ``target``, or ``None`` if it is not in this tree.
    """
    for requirement in requirements:
        if requirement.key.serial == target.key.serial:
            return [requirement]
        below = _path_to(requirement.children, target)
        if below is not None:
            return [requirement, *below]
    return None


def ancestors(requirements: Iterable[Requirement], target: Requirement) -> list[Requirement]:
    """Return the ancestors of a requirement, outermost first.

    The chain is the single strongest piece of context available for a requirement,
    because a requirement's own name is only a title: ``3. Functional Requirements``
    -> ``Source of basic data`` -> ``File import`` says far more than ``File
    import`` alone.

    Args:
        requirements: The tree's root requirements.
        target: The resolved target requirement.

    Returns:
        The chain from the top-level ancestor down to the direct parent, excluding
        the target itself. Empty for a top-level requirement, and for a target that
        is not part of this tree.
    """
    path = _path_to(requirements, target)
    if path is None:
        return []
    return path[:-1]


def siblings(requirements: Iterable[Requirement], target: Requirement) -> list[Requirement]:
    """Return the requirements sharing a parent with the target, in tree order.

    Siblings carry scope boundaries that the target's own title does not: knowing
    that ``Automatic discount`` sits beside ``Dealer allows discount`` says where
    one ends and the other begins.

    Args:
        requirements: The tree's root requirements.
        target: The resolved target requirement.

    Returns:
        The parent's other children, or the other top-level requirements when the
        target is itself top-level. Excludes the target.
    """
    chain = ancestors(requirements, target)
    pool = chain[-1].children if chain else list(requirements)
    return [node for node in pool if node.key.serial != target.key.serial]


def subtree(target: Requirement) -> list[tuple[int, Requirement]]:
    """Return the target's descendants paired with their depth below it.

    Args:
        target: The resolved target requirement.

    Returns:
        ``(depth, requirement)`` pairs in depth-first order, where a direct child
        has depth 1. Empty for a leaf. Depth is relative to the target, so it maps
        straight onto indentation when rendered.
    """
    collected: list[tuple[int, Requirement]] = []

    def walk(nodes: Iterable[Requirement], depth: int) -> None:
        for node in nodes:
            collected.append((depth, node))
            walk(node.children, depth + 1)

    walk(target.children, 1)
    return collected


#: Requirement attributes rendered on the detail line, in order.
DETAIL_ATTRIBUTES: tuple[tuple[str, Callable[[Requirement], str | None]], ...] = (
    ("version", lambda requirement: requirement.version),
    ("status", lambda requirement: requirement.status),
    ("priority", lambda requirement: requirement.priority),
    ("owner", lambda requirement: requirement.owner),
)


def render_line(requirement: Requirement, depth: int = 0) -> str:
    """Render a requirement as one indented line: identifier and title only.

    Used where breadth matters more than detail -- the ranked related requirements
    of tier 6, where thousands of candidates make every attribute a cost.

    Args:
        requirement: The requirement to render.
        depth: Indentation level; two spaces per level.

    Returns:
        A single line, without a trailing newline.
    """
    return f"{'  ' * depth}- {requirement.extendedID}: {requirement.name}"


def render_detail(requirement: Requirement, depth: int = 0) -> str:
    """Render a requirement with its attributes and populated UDFs.

    Attributes that are unset and UDFs whose value is blank are omitted rather than
    rendered empty: a baseline carries UDFs for every requirement whether or not
    they were filled in, and ``Business Units:`` with nothing after it is noise the
    model has to read past.

    Args:
        requirement: The requirement to render.
        depth: Indentation level of the title line; two spaces per level. Attribute
            and UDF lines are indented one level further.

    Returns:
        One to several lines, without a trailing newline.
    """
    lines = [render_line(requirement, depth)]
    indent = "  " * (depth + 1)

    attributes = [
        f"{label}: {value}"
        for label, value_of in DETAIL_ATTRIBUTES
        if (value := value_of(requirement))
    ]
    if attributes:
        lines.append(indent + " | ".join(attributes))

    lines.extend(
        f"{indent}{udf.name}: {udf.value}" for udf in requirement.udfs if udf.value.strip()
    )

    return "\n".join(lines)
