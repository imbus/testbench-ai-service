from unittest.mock import MagicMock

import pytest
import requests

from testbench_ai_service.llm.base import LLMProvider
from testbench_ai_service.models.agent import ElementType, ExecutionContext
from testbench_ai_service.models.config import LLMConfig, PromptConfig
from testbench_ai_service.models.language import LanguageOption
from testbench_ai_service.models.testbench import FilterInfo, FilteringOptions
from testbench_ai_service.models.testbench import (  # aliased: pytest would try to collect Test* classes
    TestCaseSetNode as TCSNode,
)
from testbench_ai_service.models.testbench import (
    TestFilterType as FilterType,
)
from testbench_ai_service.models.testbench import (
    TestStructureItemBaseInformation as ItemBaseInfo,
)
from testbench_ai_service.models.testbench import (
    TestStructureTree as StructureTree,
)
from testbench_ai_service.models.testbench import (
    TestThemeNode as ThemeNode,
)
from testbench_ai_service.utils import testbench as testbench_utils
from testbench_ai_service.utils.testbench import (
    get_project_name,
    get_test_case_set_nodes,
    get_user_key,
    post_project_tov_structure,
)


class TestGetUserKey:
    """Tests for ``get_user_key``."""

    def test_returns_user_key_from_own_user_data_response(self):
        conn = MagicMock()
        conn.server_url = "https://tb/api/"
        conn.session.get.return_value.json.return_value = {"key": "u42"}
        result = get_user_key(conn)
        assert result == "u42"
        conn.session.get.assert_called_once_with("https://tb/api/2/users/self")

    def test_http_error_propagates(self):
        conn = MagicMock()
        conn.server_url = "https://tb/api/"
        conn.session.get.side_effect = requests.exceptions.HTTPError("401 Unauthorized")
        with pytest.raises(requests.exceptions.HTTPError):
            get_user_key(conn)

    def test_connection_error_propagates(self):
        conn = MagicMock()
        conn.server_url = "https://tb/api/"
        conn.session.get.side_effect = requests.exceptions.ConnectionError("timeout")
        with pytest.raises(requests.exceptions.ConnectionError):
            get_user_key(conn)


class TestGetProjectName:
    """Tests for ``get_project_name``."""

    def test_returns_name_from_project_dict(self):
        conn = MagicMock()
        conn.get_project.return_value = {"name": "Car Configurator"}
        assert get_project_name(conn, "pk1") == "Car Configurator"

    def test_raises_when_get_project_raises(self):
        conn = MagicMock()
        conn.get_project.side_effect = RuntimeError("not found")
        with pytest.raises(RuntimeError):
            get_project_name(conn, "pk_missing")


def _make_execution_context(**overrides):
    defaults = {
        "user_key": "u1",
        "project_name": "Car Configurator",
        "project_key": "pk",
        "tov_key": "tv1",
        "language": LanguageOption.ENGLISH,
        "llm_config": LLMConfig(provider=LLMProvider.OPENAI, model="gpt-4o"),
        "prompt_config": PromptConfig(file="prompts/test.yaml"),
        "templates_dir": "templates",
    }
    defaults.update(overrides)
    return ExecutionContext(**defaults)


def _make_base(unique_id: str) -> ItemBaseInfo:
    return ItemBaseInfo(
        key=f"key-{unique_id}",
        numbering="1",
        path="/root",
        parentKey="parent",
        name=unique_id,
        uniqueID=unique_id,
        matchesFilter=True,
    )


def _make_tcs_node(unique_id: str) -> TCSNode:
    return TCSNode(base=_make_base(unique_id))


def _make_tt_node(unique_id: str) -> ThemeNode:
    return ThemeNode(base=_make_base(unique_id), filters=[])


class TestGetTestCaseSetNodes:
    """Tests for ``get_test_case_set_nodes``."""

    def test_returns_empty_without_tov_key(self):
        context = _make_execution_context(tov_key=None, element_type=ElementType.TESTTHEME)
        assert get_test_case_set_nodes(MagicMock(), context) == []

    def test_returns_empty_for_unsupported_element_type(self):
        context = _make_execution_context(element_type=ElementType.REQUIREMENT)
        assert get_test_case_set_nodes(MagicMock(), context) == []

    def test_testcaseset_context_returns_the_root_node(self, monkeypatch):
        root = _make_tcs_node("CarConfig-TC-7")
        monkeypatch.setattr(
            testbench_utils,
            "get_test_structure_tree",
            lambda **_: StructureTree(root=root, nodes=[]),
        )
        context = _make_execution_context(element_type=ElementType.TESTCASESET)

        assert get_test_case_set_nodes(MagicMock(), context) == [root]

    def test_test_case_sets_of_any_project_prefix_are_returned(self, monkeypatch):
        """The uniqueID prefix is project-specific, not the demo project's ``iTB``."""
        nodes = [
            _make_tcs_node("iTB-TC-66"),
            _make_tcs_node("CarConfig-TC-7"),
            _make_tcs_node("My Project_2-TC-001"),
        ]
        monkeypatch.setattr(
            testbench_utils,
            "get_test_structure_tree",
            lambda **_: StructureTree(root=None, nodes=nodes),
        )
        context = _make_execution_context(element_type=ElementType.TESTTHEME)

        result = get_test_case_set_nodes(MagicMock(), context)

        assert [node.base.uniqueID for node in result] == [
            "iTB-TC-66",
            "CarConfig-TC-7",
            "My Project_2-TC-001",
        ]

    def test_nodes_whose_unique_id_is_not_a_test_case_set_are_excluded(self, monkeypatch):
        """``TestStructureTree.nodes`` is an undiscriminated union, so a test theme can
        parse as a ``TestCaseSetNode``. The uniqueID suffix is the reliable guard."""
        nodes = [
            _make_tcs_node("CarConfig-TT-4091"),
            _make_tcs_node("CarConfig-TC-7"),
        ]
        monkeypatch.setattr(
            testbench_utils,
            "get_test_structure_tree",
            lambda **_: StructureTree(root=None, nodes=nodes),
        )
        context = _make_execution_context(element_type=ElementType.TESTTHEME)

        result = get_test_case_set_nodes(MagicMock(), context)

        assert [node.base.uniqueID for node in result] == ["CarConfig-TC-7"]

    def test_test_themes_are_excluded(self, monkeypatch):
        nodes = [_make_tt_node("CarConfig-TT-4091"), _make_tcs_node("CarConfig-TC-7")]
        monkeypatch.setattr(
            testbench_utils,
            "get_test_structure_tree",
            lambda **_: StructureTree(root=None, nodes=nodes),
        )
        context = _make_execution_context(element_type=ElementType.TESTTHEME)

        result = get_test_case_set_nodes(MagicMock(), context)

        assert [node.base.uniqueID for node in result] == ["CarConfig-TC-7"]


class TestPostProjectTovStructure:
    """Tests for ``post_project_tov_structure``."""

    @staticmethod
    def _conn_returning_empty_tree() -> MagicMock:
        conn = MagicMock()
        conn.server_url = "https://tb:9443/api/"
        conn.session.post.return_value.json.return_value = {"root": None, "nodes": []}
        return conn

    def _posted_body(self, **kwargs) -> dict:
        conn = self._conn_returning_empty_tree()
        post_project_tov_structure(conn, "310023", "230013", **kwargs)
        return conn.session.post.call_args.kwargs["json"]

    def test_requests_a_pruned_tree(self):
        """Both suppress flags must be sent, not left to the server's default.

        Without ``suppressFilteredData`` the server returns the whole subtree annotated
        with filter state instead of pruning it.  On a large root with a filter attached
        that is the work that made TestBench stall past its own 75 s socket limit, so
        the flags are what keep the request answerable - they are not a preference.
        """
        body = self._posted_body()
        assert body["suppressFilteredData"] is True
        assert body["suppressEmptyTestThemes"] is True

    def test_flags_are_sent_alongside_a_filter(self):
        """The filtered case is the one that stalled, so it must carry the flags too."""
        body = self._posted_body(
            root_uid="ITBEXP-TT-10667",
            filtering=FilteringOptions(
                appliedFilters=[
                    FilterInfo(
                        name="Neuer Filter",
                        filterType=FilterType.TestCaseSet,
                        testThemeUID="ITBEXP-TT-10671",
                    )
                ]
            ),
        )
        assert body["suppressFilteredData"] is True
        assert body["suppressEmptyTestThemes"] is True
        assert body["treeRootUID"] == "ITBEXP-TT-10667"
        assert body["filters"][0]["testThemeUID"] == "ITBEXP-TT-10671"

    def test_posts_to_the_tov_structure_endpoint(self):
        conn = self._conn_returning_empty_tree()
        post_project_tov_structure(conn, "310023", "230013")
        url = conn.session.post.call_args.args[0]
        assert url == "https://tb:9443/api/2/projects/310023/tovs/230013/structure"
