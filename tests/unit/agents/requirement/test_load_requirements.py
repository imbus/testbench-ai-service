"""Tests for loading the requirements the agent works from."""

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import requests

from testbench_ai_service.agents.generate_test_idears import utils as utils_module
from testbench_ai_service.agents.generate_test_idears.model import (
    ExtendedRequirement,
    RequirementAgentArgs,
)
from testbench_ai_service.agents.generate_test_idears.utils import (
    fetch_requirement_details,
    load_requirements,
)
from testbench_ai_service.models.testbench import FilteringOptions, RequirementAssignment

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


class TestFetchRequirementDetails:
    async def test_uses_the_tov_data_only_without_an_rm_service(self):
        conn = _conn()
        assignment = RequirementAssignment.model_validate(ASSIGNMENT)

        extended = await fetch_requirement_details(conn, RequirementAgentArgs(), TOV, [assignment])

        assert extended == [ExtendedRequirement.from_assignment(assignment)]
        conn.legacy_session.get.assert_not_called()

    async def test_the_first_baseline_that_knows_the_requirement_wins(self, rm):
        rm.known = {("Old", "473"), ("New", "473")}

        (extended,) = await fetch_requirement_details(MagicMock(), RM_ARGS, TOV, [_assignment()])

        assert extended.baseline == "Old"
        assert [url for url, _ in rm.posted] == [_rm_url("Old")]

    async def test_keeps_the_order_of_the_requirements(self, rm):
        rm.known = {("New", "1"), ("Old", "2"), ("New", "3")}
        assignments = [_assignment(requirement_id) for requirement_id in ("1", "2", "3")]

        extended = await fetch_requirement_details(MagicMock(), RM_ARGS, TOV, assignments)

        assert [requirement.key.id for requirement in extended] == ["1", "2", "3"]
        assert [requirement.baseline for requirement in extended] == ["New", "Old", "New"]

    async def test_falls_back_to_the_tov_data_warning_once(self, rm, caplog):
        assignment = _assignment()

        with caplog.at_level(logging.DEBUG, logger="testbench_ai_service"):
            extended = await fetch_requirement_details(MagicMock(), RM_ARGS, TOV, [assignment])

        assert extended == [ExtendedRequirement.from_assignment(assignment)]
        assert len(rm.posted) == 2
        warnings = [record for record in caplog.records if record.levelno >= logging.WARNING]
        assert [
            record.getMessage() for record in warnings if "not found" in record.getMessage()
        ] == [
            "Requirement '473' (version '1') was not found in any baseline of repository "
            "'MS Excel'; continuing with its TOV data only"
        ]

    @pytest.mark.parametrize(
        "failure",
        [
            {"status_code": 500},
            {"error": requests.exceptions.ConnectionError("refused")},
            {"error": requests.exceptions.Timeout("slow")},
            {"invalid_body": True},
        ],
        ids=["server-error", "unreachable", "timeout", "invalid-body"],
    )
    async def test_an_rm_failure_falls_back_to_the_tov_data(self, rm, failure):
        rm.known = {("Old", "473"), ("New", "473")}
        for name, value in failure.items():
            setattr(rm, name, value)
        assignment = _assignment()

        extended = await fetch_requirement_details(MagicMock(), RM_ARGS, TOV, [assignment])

        assert extended == [ExtendedRequirement.from_assignment(assignment)]
        assert extended[0].description is None
        assert extended[0].documents is None

    async def test_a_failing_baseline_does_not_stop_the_next_one(self, rm):
        rm.known = {("New", "473")}
        rm.failing_baselines = {"Old"}

        (extended,) = await fetch_requirement_details(MagicMock(), RM_ARGS, TOV, [_assignment()])

        assert extended.baseline == "New"
        assert extended.description == "Details"


class TestBaselineDiscovery:
    """Without the TOV's baselines, the RM service's own projects and baselines are searched."""

    async def test_a_jwt_connection_searches_the_rm_projects_without_asking_testbench(self, rm):
        rm.rm_projects = {"Shop": [_rm_baseline("B1")]}
        rm.known = {("B1", "473")}

        (extended,) = await fetch_requirement_details(_jwt_conn(), RM_ARGS, TOV, [_assignment()])

        assert rm.tov_baselines_calls == 0
        assert extended.baseline == "B1"
        assert [url for url, _ in rm.posted] == [_rm_url("B1")]

    async def test_a_failing_tov_baseline_lookup_falls_back_to_the_search(self, rm):
        rm.tov_baselines_error = requests.exceptions.HTTPError("403 Client Error: Forbidden")
        rm.rm_projects = {"Shop": [_rm_baseline("B1")]}
        rm.known = {("B1", "473")}

        (extended,) = await fetch_requirement_details(MagicMock(), RM_ARGS, TOV, [_assignment()])

        assert rm.tov_baselines_calls == 1
        assert extended.baseline == "B1"

    async def test_searches_every_rm_project_when_none_are_configured(self, rm):
        rm.rm_projects = {"Other": [_rm_baseline("O1")], "Shop": [_rm_baseline("S1")]}
        rm.known = {("S1", "473")}

        (extended,) = await fetch_requirement_details(_jwt_conn(), RM_ARGS, TOV, [_assignment()])

        assert extended.baseline == "S1"
        assert rm.fetched[0] == f"{RM_URL}projects"
        assert [url for url, _ in rm.posted] == [
            f"{RM_URL}projects/Other/baselines/O1/extended-requirement",
            _rm_url("S1"),
        ]

    async def test_searches_only_the_configured_rm_projects_in_their_order(self, rm):
        rm.rm_projects = {
            "Other": [_rm_baseline("O1")],
            "Shop": [_rm_baseline("S1")],
            "Ignored": [_rm_baseline("I1")],
        }
        args = RM_ARGS.model_copy(update={"rm_projects": ["Shop", "Other"]})

        await fetch_requirement_details(_jwt_conn(), args, TOV, [_assignment()])

        assert f"{RM_URL}projects" not in rm.fetched
        assert [url for url, _ in rm.posted] == [
            _rm_url("S1"),
            f"{RM_URL}projects/Other/baselines/O1/extended-requirement",
        ]

    async def test_tries_the_current_baseline_of_a_project_first(self, rm):
        rm.rm_projects = {
            "Shop": [
                _rm_baseline("Old", "LOCKED"),
                _rm_baseline("Current Baseline", "CURRENT"),
                _rm_baseline("Draft", "UNLOCKED"),
            ]
        }

        await fetch_requirement_details(_jwt_conn(), RM_ARGS, TOV, [_assignment()])

        assert [url for url, _ in rm.posted] == [
            _rm_url("Current Baseline"),
            _rm_url("Old"),
            _rm_url("Draft"),
        ]

    async def test_lists_the_baselines_once_for_all_requirements(self, rm):
        rm.rm_projects = {"Shop": [_rm_baseline("B1")]}
        rm.known = {("B1", "1"), ("B1", "2")}
        assignments = [_assignment(requirement_id) for requirement_id in ("1", "2")]

        extended = await fetch_requirement_details(_jwt_conn(), RM_ARGS, TOV, assignments)

        assert [requirement.baseline for requirement in extended] == ["B1", "B1"]
        assert rm.fetched == [f"{RM_URL}projects", f"{RM_URL}projects/Shop/baselines"]

    async def test_a_failing_project_does_not_stop_the_next_one(self, rm):
        rm.rm_projects = {"Broken": [], "Shop": [_rm_baseline("B1")]}
        rm.failing_projects = {"Broken"}
        rm.known = {("B1", "473")}

        (extended,) = await fetch_requirement_details(_jwt_conn(), RM_ARGS, TOV, [_assignment()])

        assert extended.baseline == "B1"

    async def test_an_unreachable_rm_service_falls_back_to_the_tov_data(self, rm):
        rm.projects_error = requests.exceptions.ConnectionError("refused")
        assignment = _assignment()

        extended = await fetch_requirement_details(_jwt_conn(), RM_ARGS, TOV, [assignment])

        assert extended == [ExtendedRequirement.from_assignment(assignment)]
        assert rm.posted == []


#: A syntactically valid JWT, as TestBench issues them for scoped access.
JWT = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJzdWIiOiIxMjM0NTY3ODkwIn0"
    ".dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
)


def _jwt_conn() -> MagicMock:
    conn = MagicMock()
    conn.session_token = JWT
    return conn


def _rm_baseline(name: str, baseline_type: str = "UNLOCKED") -> dict:
    return {"name": name, "date": "2026-01-01T00:00:00.000Z", "type": baseline_type}


RM_URL = "http://rm/"
RM_ARGS = RequirementAgentArgs(rm_service_url=RM_URL, rm_username="u", rm_password="p")
#: Two baselines of the requirements' repository, in the order the TOV lists them.
BASELINES = [
    {"repository": "MS Excel", "name": name, "reqProjectName": "Shop"} for name in ("Old", "New")
]


def _assignment(requirement_id: str = "473") -> RequirementAssignment:
    return RequirementAssignment.model_validate(ASSIGNMENT | {"id": requirement_id})


def _rm_url(baseline: str) -> str:
    return f"{RM_URL}projects/Shop/baselines/{baseline}/extended-requirement"


@pytest.fixture
def rm(monkeypatch):
    """Fake the TOV baselines and the RM service; ``known`` holds (baseline, id) pairs."""
    state = SimpleNamespace(
        known=set(),
        posted=[],
        status_code=None,
        error=None,
        invalid_body=False,
        failing_baselines=set(),
    )

    def _post(url, json):
        state.posted.append((url, json))
        baseline = url.split("/baselines/")[1].split("/")[0]
        if state.error is not None:
            raise state.error
        response = MagicMock()
        if baseline in state.failing_baselines:
            raise requests.exceptions.ConnectionError("refused")
        if state.invalid_body:
            response.status_code = 200
            response.json.side_effect = ValueError("not JSON")
        elif state.status_code is not None:
            response.status_code = state.status_code
            response.raise_for_status.side_effect = requests.exceptions.HTTPError()
        elif (baseline, json["id"]) in state.known:
            response.status_code = 200
            response.json.return_value = {
                "name": f"Requirement {json['id']}",
                "extendedID": f"ER_{json['id']}",
                "key": {"id": json["id"], "version": json["version"]},
                "owner": "someone",
                "status": "open",
                "priority": "high",
                "requirement": True,
                "description": "Details",
                "documents": [],
                "baseline": baseline,
            }
        else:
            response.status_code = 404
        return response

    def _tov_baselines(_conn, _tov):
        state.tov_baselines_calls += 1
        if state.tov_baselines_error is not None:
            raise state.tov_baselines_error
        return BASELINES

    state.fetched = []
    state.rm_projects = {}
    state.projects_error = None
    state.failing_projects = set()
    state.tov_baselines_error = None
    state.tov_baselines_calls = 0
    session = MagicMock()
    session.__enter__.return_value = session
    session.post.side_effect = _post
    session.get.side_effect = _fake_rm_get(state)
    monkeypatch.setattr(utils_module, "get_tov_baselines", _tov_baselines)
    monkeypatch.setattr(utils_module, "_rm_session", lambda _args: session)
    return state


def _fake_rm_get(state: SimpleNamespace):
    """Fake the RM service's project and baseline listings from ``state.rm_projects``."""

    def _get(url):
        state.fetched.append(url)
        path = url.removeprefix(RM_URL)
        response = MagicMock()
        if path == "projects":
            if state.projects_error is not None:
                raise state.projects_error
            response.json.return_value = list(state.rm_projects)
        else:
            project = path.split("/")[1]
            if project in state.failing_projects:
                raise requests.exceptions.HTTPError("500 Server Error")
            response.json.return_value = state.rm_projects[project]
        return response

    return _get
