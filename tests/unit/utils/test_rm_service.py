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
