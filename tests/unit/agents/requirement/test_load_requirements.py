"""Tests for loading the requirements the agent works from."""

from unittest.mock import MagicMock

from testbench_ai_service.agents.requirement.utils import load_requirements
from testbench_ai_service.models.testbench import FilteringOptions

SERVER = "https://tb/"
PROJECT = "7"
TOV = "42"
CYCLE = "99"
ROOT = "root-uid"

ASSIGNMENT = {
    "key": "473",
    "name": "Requirement 473",
    "id": "473",
    "extendedId": "ER_1",
    "version": "1",
    "owner": "someone",
    "status": "open",
    "priority": "high",
    "repositoryId": "MS Excel",
}


def _conn(requirements: list[dict] | None = None) -> MagicMock:
    conn = MagicMock()
    conn.server_url = SERVER
    conn.session.post.return_value.json.return_value = (
        requirements if requirements is not None else [ASSIGNMENT]
    )
    return conn


def _posted(conn: MagicMock) -> tuple[str, dict]:
    (url,), kwargs = conn.session.post.call_args
    return url, kwargs["json"]


class TestLoadRequirements:
    async def test_parses_the_tov_requirements(self):
        conn = _conn()

        loaded = await load_requirements(conn, PROJECT, ROOT, TOV)

        assert [r.extendedId for r in loaded] == ["ER_1"]
        assert _posted(conn)[0] == f"{SERVER}2/projects/{PROJECT}/tovs/{TOV}/requirements"

    async def test_uses_the_cycle_endpoint_when_a_cycle_is_given(self):
        conn = _conn()

        await load_requirements(conn, PROJECT, ROOT, TOV, CYCLE)

        assert _posted(conn)[0] == f"{SERVER}2/projects/{PROJECT}/cycles/{CYCLE}/requirements"

    async def test_sends_only_the_root_uid_without_filtering(self):
        conn = _conn()

        await load_requirements(conn, PROJECT, ROOT, TOV)

        assert _posted(conn)[1] == {"treeRootUID": ROOT}

    async def test_sends_the_filtering_options_when_given(self):
        filtering = FilteringOptions.model_validate(
            {
                "appliedFilters": [{"name": "f", "filterType": "TestTheme", "testThemeUID": "t1"}],
                "excludedTestThemes": ["t2"],
                "labelFilter": "smoke",
            }
        )
        conn = _conn()

        await load_requirements(conn, PROJECT, ROOT, TOV, filtering=filtering)

        applied = [{"name": "f", "filterType": "TestTheme", "testThemeUID": "t1"}]
        assert _posted(conn)[1] == {
            "treeRootUID": ROOT,
            "filters": applied,
            "filtering": {
                "appliedFilters": applied,
                "excludedTestThemes": ["t2"],
                "labelFilter": "smoke",
            },
        }

    async def test_returns_an_empty_list_when_nothing_is_assigned(self):
        assert await load_requirements(_conn([]), PROJECT, ROOT, TOV) == []
