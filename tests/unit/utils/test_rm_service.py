"""The RM service lookup and requirement models shared by the requirement-based agents."""

import pytest
from pydantic import ValidationError

from testbench_ai_service.agents.generate_test_idears import model as generator_model
from testbench_ai_service.models.testbench import RequirementAssignment
from testbench_ai_service.utils import rm_service


def test_the_generator_reexports_the_shared_models():
    assert generator_model.Requirement is rm_service.Requirement
    assert generator_model.ExtendedRequirement is rm_service.ExtendedRequirement
    assert generator_model.ExtendedRequirementKey is rm_service.ExtendedRequirementKey


def test_the_generator_args_extend_the_rm_args():
    assert issubclass(generator_model.RequirementAgentArgs, rm_service.RmServiceArgs)


def test_the_rm_url_gets_a_trailing_slash():
    args = rm_service.RmServiceArgs(rm_service_url="http://rm", rm_username="u", rm_password="p")

    assert args.rm_service_url == "http://rm/"


def test_an_rm_url_without_credentials_is_rejected():
    with pytest.raises(ValidationError):
        rm_service.RmServiceArgs(rm_service_url="http://rm/")


def test_unknown_args_are_rejected():
    with pytest.raises(ValidationError):
        rm_service.RmServiceArgs(rm_url="http://rm/")


async def test_without_an_rm_url_every_requirement_keeps_its_tov_data():
    assignment = RequirementAssignment(
        key="473",
        name="Login",
        id="REQ-1",
        extendedId="EXT-1",
        version="1.0",
        owner="o",
        status="s",
        priority="p",
        repositoryId="repo",
    )

    (extended,) = await rm_service.fetch_requirement_details(
        None, rm_service.RmServiceArgs(), "42", [assignment]
    )

    assert extended.name == "Login"
    assert extended.description is None


def test_an_empty_rm_projects_list_is_rejected():
    with pytest.raises(ValidationError):
        rm_service.RmServiceArgs(rm_projects=[])


RM_ARGS = rm_service.RmServiceArgs(rm_service_url="http://rm/", rm_username="u", rm_password="p")
EXTENDED = rm_service.ExtendedRequirement(
    name="Logout",
    extendedID="EXT-9",
    key=rm_service.ExtendedRequirementKey(id="REQ-9", version="1.2"),
    owner="o",
    status="s",
    priority="p",
    requirement=True,
    description="<p>A user can log out.</p>",
    documents=[],
    baseline="B2",
)


@pytest.fixture
def rm(monkeypatch):
    """An RM service with two baselines; only the second one knows REQ-9."""
    state = {"versions": {("B2", "REQ-9"): "1.2"}, "asked": []}

    async def _baselines(conn, tov_key):
        return [
            {"name": "B1", "reqProjectName": "P", "repository": "r"},
            {"name": "B2", "reqProjectName": "P", "repository": "r"},
        ]

    def _version(session, url, project, baseline, req_id):
        state["asked"].append((baseline, req_id))
        return state["versions"].get((baseline, req_id))

    def _extended(session, url, project, baseline, req_id, version):
        assert (project, baseline, req_id, version) == ("P", "B2", "REQ-9", "1.2")
        return EXTENDED

    monkeypatch.setattr(rm_service, "_load_tov_baselines", _baselines)
    monkeypatch.setattr(rm_service, "get_latest_requirement_version", _version)
    monkeypatch.setattr(rm_service, "get_extended_requirement", _extended)
    return state


async def test_an_unassigned_requirement_is_read_in_its_latest_version(rm):
    found = await rm_service.find_rm_requirement(None, RM_ARGS, "42", ["555", "REQ-9"])

    assert found is EXTENDED
    assert rm["asked"] == [("B1", "555"), ("B1", "REQ-9"), ("B2", "555"), ("B2", "REQ-9")]


async def test_an_id_no_baseline_knows_is_not_found(rm):
    assert await rm_service.find_rm_requirement(None, RM_ARGS, "42", ["nope"]) is None


async def test_without_an_rm_url_nothing_is_found():
    args = rm_service.RmServiceArgs()

    assert await rm_service.find_rm_requirement(None, args, "42", ["x"]) is None


class _Response:
    def __init__(self, status, body=None):
        self.status_code = status
        self._body = body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise rm_service.requests.exceptions.HTTPError(str(self.status_code))

    def json(self):
        return self._body


class _Session:
    def __init__(self, response):
        self.response = response
        self.posted = []

    def post(self, url, json):
        self.posted.append((url, json))
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def test_the_latest_version_is_the_newest_by_date():
    session = _Session(
        _Response(
            200,
            [
                {"name": "1.0", "date": "2026-01-01T00:00:00+00:00"},
                {"name": "1.2", "date": "2026-03-01T00:00:00+00:00"},
                {"name": "1.1", "date": "2026-02-01T00:00:00+00:00"},
            ],
        )
    )

    version = rm_service.get_latest_requirement_version(session, "http://rm/", "P", "B", "R-1")

    assert version == "1.2"
    assert session.posted == [
        (
            "http://rm/projects/P/baselines/B/requirement-versions",
            {"id": "R-1", "version": "*"},
        )
    ]


@pytest.mark.parametrize(
    "response",
    [
        _Response(404),
        _Response(400),
        _Response(500),
        _Response(200, []),
        _Response(200, [{"unexpected": 1}]),
        rm_service.requests.exceptions.ReadTimeout("slow"),
    ],
)
def test_any_failure_to_read_the_versions_is_a_miss(response):
    session = _Session(response)

    assert rm_service.get_latest_requirement_version(session, "http://rm/", "P", "B", "R") is None
