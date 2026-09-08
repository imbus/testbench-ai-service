"""Tests for bridging the requirement tree to the test structure tree."""

from unittest.mock import MagicMock

from testbench_ai_service.agents.requirement.linking import collect_theme_contexts
from testbench_ai_service.agents.requirement.tree import find_requirement

BASE = "https://tb/api/"


def _theme_node(key: str, name: str, spec_key: str, parent_key: str = "root") -> dict:
    return {
        "elementType": "TestThemeNode",
        "base": {
            "key": key,
            "numbering": "1",
            "path": f"Root/{name}",
            "parentKey": parent_key,
            "name": name,
            "uniqueID": f"TT-{key}",
            "matchesFilter": True,
        },
        "spec": {"key": spec_key, "status": "InProgress"},
        "filters": [],
    }


def _tcs_node(key: str, name: str, parent_key: str) -> dict:
    return {
        "elementType": "TestCaseSetNode",
        "base": {
            "key": key,
            "numbering": "1",
            "path": f"Root/{name}",
            "parentKey": parent_key,
            "name": name,
            "uniqueID": f"TCS-{key}",
            "matchesFilter": True,
        },
        "spec": {"key": f"spec-{key}", "status": "InProgress"},
    }


def _spec(description: str = "", requirement_keys: tuple[str, ...] = ()) -> dict:
    return {
        "key": "ignored",
        "description": description,
        "reviewComment": "",
        "status": "InProgress",
        "priority": "Middle",
        "udfs": [],
        "tags": [],
        "requirements": [{"key": key, "edited": False} for key in requirement_keys],
        "references": [],
    }


def _conn(nodes: list[dict], specs: dict[str, dict]) -> MagicMock:
    """Build a connection serving one structure tree and a theme payload per spec key.

    A theme is read through the element endpoint, so the double is keyed the way that
    endpoint is: the theme's own key in the path, the specification key as a parameter.
    """
    conn = MagicMock()
    conn.server_url = BASE
    conn.session.post.return_value.json.return_value = {"root": None, "nodes": nodes}
    conn.spec_calls: list[tuple[str, str | None]] = []

    def get_project_test_theme(
        project_key: str,
        test_theme_key: str,
        specification_key: str | None = None,
        execution_key: str | None = None,
    ):
        conn.spec_calls.append((test_theme_key, specification_key))
        return {"key": test_theme_key, "spec": specs[specification_key]}

    conn.get_project_test_theme.side_effect = get_project_test_theme
    return conn


async def _collect(conn, target, core=()):
    return await collect_theme_contexts(
        conn,
        project_key="10004",
        tov_key="42",
        cycle_key=None,
        target=target,
        core_requirements=list(core),
    )


class TestCollectThemeContexts:
    async def test_finds_the_theme_linking_the_target_by_requirement_key(self, baseline):
        target = find_requirement(baseline.children, "ER_WHY299")
        conn = _conn(
            [_theme_node("t1", "Discounts", "s1"), _theme_node("t2", "Imports", "s2")],
            {"s1": _spec("Discount coverage", (target.requirementKey.serial,)), "s2": _spec()},
        )

        found = await _collect(conn, target)

        assert [context.theme_name for _, context in found] == ["Discounts"]

    async def test_also_matches_the_baseline_node_key_space(self, baseline):
        target = find_requirement(baseline.children, "ER_WHY299")
        conn = _conn(
            [_theme_node("t1", "Discounts", "s1")],
            {"s1": _spec(requirement_keys=(target.key.serial,))},
        )

        found = await _collect(conn, target)

        assert [context.theme_name for _, context in found] == ["Discounts"]

    async def test_returns_nothing_when_no_theme_links_the_target(self, baseline):
        target = find_requirement(baseline.children, "ER_WHY299")
        conn = _conn(
            [_theme_node("t1", "Discounts", "s1")],
            {"s1": _spec(requirement_keys=("999999",))},
        )

        assert await _collect(conn, target) == []

    async def test_returns_every_linked_theme(self, baseline):
        target = find_requirement(baseline.children, "ER_WHY299")
        keys = (target.requirementKey.serial,)
        conn = _conn(
            [_theme_node("t1", "Discounts", "s1"), _theme_node("t2", "Pricing", "s2")],
            {"s1": _spec(requirement_keys=keys), "s2": _spec(requirement_keys=keys)},
        )

        found = await _collect(conn, target)

        assert sorted(context.theme_name for _, context in found) == ["Discounts", "Pricing"]

    async def test_carries_the_current_description_and_the_test_case_sets_below(self, baseline):
        target = find_requirement(baseline.children, "ER_WHY299")
        conn = _conn(
            [
                _theme_node("t1", "Discounts", "s1"),
                _tcs_node("c1", "Automatic discount TCS", "t1"),
                _tcs_node("c2", "Elsewhere TCS", "t2"),
            ],
            {"s1": _spec("Existing coverage notes", (target.requirementKey.serial,))},
        )

        (_, context), *_ = await _collect(conn, target)

        assert context.description == "Existing coverage notes"
        assert context.test_case_sets == ["Automatic discount TCS"]

    async def test_reports_themes_linked_to_nearby_requirements(self, baseline):
        target = find_requirement(baseline.children, "ER_WHY299")
        neighbour = find_requirement(baseline.children, "ER_WHY298")
        conn = _conn(
            [_theme_node("t1", "Discounts", "s1"), _theme_node("t2", "Parent theme", "s2")],
            {
                "s1": _spec(requirement_keys=(target.requirementKey.serial,)),
                "s2": _spec(requirement_keys=(neighbour.requirementKey.serial,)),
            },
        )

        (_, context), *_ = await _collect(conn, target, core=[neighbour])

        assert context.related_tests == {"ER_WHY298": ["Parent theme"]}

    async def test_reads_the_theme_element_and_never_the_write_endpoint(self, baseline):
        """``/specifications/{key}`` answers ``PATCH`` alone -- reading it is a 404/400."""
        target = find_requirement(baseline.children, "ER_WHY299")
        conn = _conn(
            [_theme_node("t1", "Discounts", "s1")],
            {"s1": _spec(requirement_keys=(target.requirementKey.serial,))},
        )

        await _collect(conn, target)

        assert conn.spec_calls == [("t1", "s1")]
        conn.session.patch.assert_not_called()
        conn.session.get.assert_not_called()

    async def test_reads_one_spec_per_theme_and_none_per_test_case_set(self, baseline):
        target = find_requirement(baseline.children, "ER_WHY299")
        nodes = [_theme_node(f"t{index}", f"Theme {index}", f"s{index}") for index in range(5)]
        nodes += [_tcs_node(f"c{index}", f"TCS {index}", "t0") for index in range(40)]
        specs = {f"s{index}": _spec() for index in range(5)}
        specs["s0"] = _spec(requirement_keys=(target.requirementKey.serial,))
        conn = _conn(nodes, specs)

        await _collect(conn, target)

        assert len(conn.spec_calls) == 5
