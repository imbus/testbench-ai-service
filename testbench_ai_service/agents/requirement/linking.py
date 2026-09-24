"""Reads test-side context for the test theme test ideas are written into."""

from testbench_ai_service.models.testbench import (
    TestCaseSetNode,
    TestStructureTree,
    TestThemeNode,
)


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
