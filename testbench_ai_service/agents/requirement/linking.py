"""Bridges the requirement tree to the test structure tree.

A trigger names a requirement, but test ideas are written into a test theme's
description, so the theme has to be found from the requirement. TestBench maintains
that association on the theme side: each theme's *specification* carries a
``requirements`` list of :class:`RequirementReference`.

Two consequences shape this module.

The tree endpoint returns only ``spec.key``, ``locker`` and ``status`` for a node --
the ``requirements`` list lives on the specification detail payload. Finding the
linked theme therefore costs one specification read per test theme. That is bounded
by the number of themes in the TOV, typically tens, and never by the number of
requirements in the baseline, which can run to thousands.

Test case set specifications are deliberately *not* read. Doing so would cost a
request per test case set across the whole TOV -- the unbounded fan-out the design
rules out. Test case set names still reach the prompt, taken from the tree, which
costs nothing.
"""

import asyncio

from testbench_cli_reporter.testbench import Connection as TBConnection

from testbench_ai_service.agents.requirement.model import Requirement, ThemeContext
from testbench_ai_service.log import logger
from testbench_ai_service.models.testbench import (
    TestCaseSetNode,
    TestStructureTree,
    TestThemeNode,
    TestThemeSpecification,
)
from testbench_ai_service.utils.testbench import (
    get_test_structure_tree,
    get_test_theme_details,
)


def requirement_keys(requirement: Requirement) -> set[str]:
    """Return every key a theme specification might use to reference a requirement.

    Which of the two key spaces ``RequirementReference.key`` draws on is not
    confirmed: ``requirementKey`` identifies the requirement in the RE repository,
    ``key`` identifies its node inside one baseline. Because the two spaces share no
    values, matching against both is safe -- a reference can match at most one of
    them, so no false positive is possible and the ambiguity costs nothing.

    Args:
        requirement: The requirement to build match keys for.

    Returns:
        The candidate keys.
    """
    return {requirement.requirementKey.serial, requirement.key.serial}


async def get_theme_specification(
    conn: TBConnection,
    project_key: str,
    theme_key: str,
    spec_key: str,
) -> TestThemeSpecification:
    """Read one test theme's specification, including its requirement references.

    The specification is reached through the theme element, not through
    ``/specifications/{specificationKey}``: that path is the write endpoint and
    answers ``PATCH`` alone.

    Args:
        conn: The active TestBench connection.
        project_key: Key of the project owning the theme.
        theme_key: The theme's ``base.key`` from the structure tree.
        spec_key: The theme's ``spec.key`` from the structure tree.

    Returns:
        The parsed specification.
    """
    details = await asyncio.to_thread(
        get_test_theme_details, conn, project_key, theme_key, spec_key
    )
    return details.spec


def test_case_set_names(tree: TestStructureTree, theme: TestThemeNode) -> list[str]:
    """Return the names of the test case sets directly below a theme.

    Args:
        tree: The loaded test structure tree.
        theme: The theme whose children are wanted.

    Returns:
        The names, in tree order.
    """
    return [
        node.base.name
        for node in tree.nodes
        if isinstance(node, TestCaseSetNode) and node.base.parentKey == theme.base.key
    ]


async def collect_theme_contexts(
    conn: TBConnection,
    *,
    project_key: str,
    tov_key: str,
    cycle_key: str | None,
    target: Requirement,
    core_requirements: list[Requirement],
) -> list[tuple[TestThemeNode, ThemeContext]]:
    """Find the themes linking the target requirement and gather their context.

    The whole test structure tree is requested, deliberately without a root: the
    execution context's ``root_uid`` identifies a requirement, so passing it as a
    test structure root would filter the tree down to nothing.

    Args:
        conn: The active TestBench connection.
        project_key: Key of the project being worked in.
        tov_key: Key of the test object version holding the test structure.
        cycle_key: Key of the test cycle, when the trigger came from one.
        target: The resolved target requirement.
        core_requirements: The structural-core requirements -- ancestors, siblings
            and subtree -- whose linked themes become tier-5 context.

    Returns:
        One ``(theme node, theme context)`` pair per theme linking the target. The
        node is returned alongside because writing back needs its ``spec.key`` and
        its lock owner. Empty when no theme links the requirement.
    """
    tree = await asyncio.to_thread(
        get_test_structure_tree,
        conn=conn,
        project_key=project_key,
        tov_key=tov_key,
        cycle_key=cycle_key,
        root_uid=None,
    )

    themes = [node for node in tree.nodes if isinstance(node, TestThemeNode)]

    specifications: list[tuple[TestThemeNode, TestThemeSpecification]] = []
    for theme in themes:
        if theme.spec is None:
            continue
        specifications.append(
            (
                theme,
                await get_theme_specification(conn, project_key, theme.base.key, theme.spec.key),
            )
        )
    logger.debug(
        "Read %d theme specification(s) from %d tree node(s) while resolving requirement '%s'",
        len(specifications),
        len(tree.nodes),
        target.extendedID,
    )
    target_keys = requirement_keys(target)
    related_tests: dict[str, list[str]] = {}
    for requirement in core_requirements:
        keys = requirement_keys(requirement)
        names = [
            theme.base.name
            for theme, specification in specifications
            if keys & {reference.key for reference in specification.requirements}
        ]
        if names:
            related_tests[requirement.extendedID] = names
    contexts = [
        (
            theme,
            ThemeContext(
                theme_name=theme.base.name,
                description=specification.description,
                test_case_sets=test_case_set_names(tree, theme),
                related_tests=related_tests,
            ),
        )
        for theme, specification in specifications
        if target_keys & {reference.key for reference in specification.requirements}
    ]

    if not contexts:
        # Only the finding is reported here; what an unlinked requirement means for
        # the run is the caller's to decide and to log.
        logger.info(
            "None of the %d theme(s) read links requirement '%s'",
            len(specifications),
            target.extendedID,
        )

    return contexts
