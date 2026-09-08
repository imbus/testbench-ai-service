"""Tests for pure navigation over a requirement tree."""

from testbench_ai_service.agents.requirement.model import Requirement
from testbench_ai_service.agents.requirement.tree import (
    ancestors,
    find_requirement,
    render_detail,
    render_line,
    siblings,
    subtree,
)


def _req(
    extended_id: str,
    *,
    id_: str | None = None,
    serial: str = "1",
    requirement_serial: str = "2",
    children: list[Requirement] | None = None,
) -> Requirement:
    return Requirement(
        key={"serial": serial},
        requirementKey={"serial": requirement_serial},
        baselineKey={"serial": "3"},
        id=id_ if id_ is not None else extended_id,
        extendedID=extended_id,
        name=f"Requirement {extended_id}",
        children=children or [],
    )


def _find(baseline, extended_id: str) -> Requirement:
    found = find_requirement(baseline.children, extended_id)
    assert found is not None, f"fixture is missing {extended_id}"
    return found


class TestAncestors:
    def test_returns_path_from_top_level_down_to_direct_parent(self, baseline):
        target = _find(baseline, "ER_WHY299")

        chain = ancestors(baseline.children, target)

        assert [node.extendedID for node in chain] == ["EF_3100077", "ER_WHY298"]

    def test_is_empty_for_a_top_level_requirement(self, baseline):
        target = _find(baseline, "EF_3100077")

        assert ancestors(baseline.children, target) == []


class TestSiblings:
    def test_returns_the_other_children_of_the_same_parent(self, baseline):
        target = _find(baseline, "ER_WHY299")

        found = siblings(baseline.children, target)

        assert [node.extendedID for node in found] == ["ER_WHY300"]

    def test_returns_the_other_top_level_requirements_for_a_root_node(self, baseline):
        target = _find(baseline, "EF_3100077")

        found = siblings(baseline.children, target)

        assert [node.extendedID for node in found] == [
            "EF_3100081",
            "EF_3100078",
            "EF_3100079",
        ]

    def test_is_empty_when_the_target_is_an_only_child(self, baseline):
        target = _find(baseline, "ER_WHY299")
        parent = _find(baseline, "ER_WHY298")
        parent.children = [target]

        assert siblings(baseline.children, target) == []


class TestSubtree:
    def test_returns_descendants_paired_with_their_relative_depth(self, baseline):
        target = _find(baseline, "EF_3100077")

        assert [(depth, node.extendedID) for depth, node in subtree(target)] == [
            (1, "ER_WHY297"),
            (1, "ER_WHY298"),
            (2, "ER_WHY299"),
            (2, "ER_WHY300"),
        ]

    def test_is_empty_for_a_leaf(self, baseline):
        target = _find(baseline, "ER_DSGN309")

        assert subtree(target) == []


class TestFindRequirement:
    def test_finds_a_nested_requirement_by_extended_id(self, baseline):
        found = find_requirement(baseline.children, "ER_WHAT306")

        assert found is not None
        assert found.name == "Import from OEM host"

    def test_returns_none_for_an_unknown_uid(self, baseline):
        assert find_requirement(baseline.children, "ER_NOPE999") is None

    def test_falls_back_to_id_when_no_extended_id_matches(self):
        tree = [_req("EXT-1", id_="PLAIN-1")]

        found = find_requirement(tree, "PLAIN-1")

        assert found is not None
        assert found.extendedID == "EXT-1"

    def test_falls_back_to_requirement_key_serial(self):
        tree = [_req("EXT-1", requirement_serial="475")]

        found = find_requirement(tree, "475")

        assert found is not None
        assert found.extendedID == "EXT-1"

    def test_falls_back_to_node_key_serial(self):
        tree = [_req("EXT-1", serial="4491", requirement_serial="475")]

        found = find_requirement(tree, "4491")

        assert found is not None
        assert found.extendedID == "EXT-1"

    def test_prefers_an_extended_id_match_over_an_id_match(self):
        tree = [_req("OTHER", id_="SHARED"), _req("SHARED", id_="OTHER")]

        found = find_requirement(tree, "SHARED")

        assert found is not None
        assert found.extendedID == "SHARED"


class TestRenderLine:
    def test_renders_a_single_indented_line(self, baseline):
        target = _find(baseline, "ER_WHY299")

        assert render_line(target, depth=2) == "    - ER_WHY299: Automatic discount"

    def test_omits_attributes_and_udfs_to_stay_cheap(self, baseline):
        target = _find(baseline, "ER_WHY299")

        rendered = render_line(target)

        assert rendered == "- ER_WHY299: Automatic discount"
        assert "Marketing" not in rendered


class TestRenderDetail:
    def test_renders_attributes_and_udfs_below_the_title(self, baseline):
        target = _find(baseline, "ER_WHY299")

        assert render_detail(target) == (
            "- ER_WHY299: Automatic discount\n"
            "  version: 1.1 | status: Accepted | priority: Essential | owner: RE-Manager\n"
            "  Business Units: Marketing\n"
            "  Owner Priorität: Higher"
        )

    def test_indents_every_line_by_the_given_depth(self, baseline):
        target = _find(baseline, "ER_WHY299")

        rendered = render_detail(target, depth=1)

        assert all(line.startswith("  ") for line in rendered.splitlines())
        assert rendered.splitlines()[0] == "  - ER_WHY299: Automatic discount"

    def test_skips_udfs_whose_value_is_blank(self, baseline):
        target = _find(baseline, "ER_WHY300")

        rendered = render_detail(target)

        assert "Business Units" not in rendered
        assert "Owner Priorität: Even Higher" in rendered

    def test_omits_attributes_that_are_unset(self):
        target = _req("EXT-1")

        assert render_detail(target) == "- EXT-1: Requirement EXT-1"
