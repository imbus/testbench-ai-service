"""Finding the triggered requirement and the test cases linked to it."""

from types import SimpleNamespace

import pytest

from testbench_ai_service.models.testbench import RequirementAssignment
from testbench_ai_service.utils.rm_service import ExtendedRequirement, RmServiceArgs
from testbench_ai_service.utils.traceability import context as context_module
from testbench_ai_service.utils.traceability.context import (
    find_requirement,
    linked_set_keys,
    linked_test_cases,
    load_requirement_context,
    load_unassigned_requirement,
    test_case_set_detail,
)
from tests.unit.utils.traceability.fakes import call, case, test_case_set

REQ = "473"


def _assignment(key=REQ, uid="REQ-1", extended="EXT-1") -> RequirementAssignment:
    return RequirementAssignment(
        key=key,
        name="Login",
        id=uid,
        extendedId=extended,
        version="1.0",
        owner="o",
        status="s",
        priority="p",
        repositoryId="repo",
    )


class TestLinkedTestCases:
    def test_a_whole_set_link_contributes_every_test_case(self):
        tcs = test_case_set("1", "/A", links=[REQ], cases=[case("TC-1"), case("TC-2")])

        whole, cases = linked_test_cases(tcs, REQ)

        assert whole is True
        assert [c.uniqueID for c in cases] == ["TC-1", "TC-2"]

    def test_a_test_case_link_contributes_only_that_test_case(self):
        tcs = test_case_set("1", "/A", cases=[case("TC-1", links=[REQ]), case("TC-2")])

        whole, cases = linked_test_cases(tcs, REQ)

        assert whole is False
        assert [c.uniqueID for c in cases] == ["TC-1"]

    def test_whole_set_link_and_case_link_do_not_duplicate_cases(self):
        tcs = test_case_set("1", "/A", links=[REQ], cases=[case("TC-1", links=[REQ])])

        _, cases = linked_test_cases(tcs, REQ)

        assert [c.uniqueID for c in cases] == ["TC-1"]


class TestLinkedSetKeys:
    def test_unlinked_sets_are_left_out_and_the_rest_sorted_by_path(self):
        catalog = {
            "b": test_case_set("b", "/B", links=[REQ], cases=[case("TC-B")]),
            "x": test_case_set("x", "/X", cases=[case("TC-X", links=["999"])]),
            "a": test_case_set("a", "/A", cases=[case("TC-A", links=[REQ])]),
        }

        assert linked_set_keys(catalog, REQ) == ["a", "b"]

    def test_an_empty_set_linked_as_a_whole_is_listed(self):
        catalog = {"e": test_case_set("e", "/E", links=[REQ])}

        assert linked_set_keys(catalog, REQ) == ["e"]


class TestFindRequirement:
    def test_root_key_is_matched_against_the_testbench_key(self):
        assignments = [_assignment("1"), _assignment(REQ, uid="REQ-2")]

        assert find_requirement(assignments, REQ, None).id == "REQ-2"

    def test_root_uid_is_matched_against_id_and_extended_id(self):
        assignments = [_assignment("1", uid="REQ-1", extended="EXT-9")]

        assert find_requirement(assignments, None, "EXT-9").key == "1"
        assert find_requirement(assignments, None, "REQ-1").key == "1"

    def test_an_unknown_requirement_is_none(self):
        assert find_requirement([_assignment()], "nope", "nope") is None


async def test_the_context_holds_the_linked_test_cases_with_their_calls(monkeypatch):
    sequence = [
        call("Open login page", phase="Setup"),
        call("Check message", check=True, text="Locked", empty=""),
    ]
    catalog = {
        "1": test_case_set(
            "1", "/A", links=[REQ], cases=[case("TC-1", user="bob")], sequence=sequence
        ),
        "2": test_case_set("2", "/B", cases=[case("TC-2", links=["999"])]),
        "3": test_case_set("3", "/C", cases=[case("TC-3", links=[REQ])]),
    }
    monkeypatch.setattr(context_module, "get_requirements", lambda *args: [_assignment()])
    monkeypatch.setattr(context_module, "get_test_case_set_catalog", lambda *args: catalog)

    async def _details(_conn, _args, _tov, assignments):
        return [ExtendedRequirement.from_assignment(assignments[0])]

    monkeypatch.setattr(context_module, "fetch_requirement_details", _details)

    loaded = await load_requirement_context(
        SimpleNamespace(), RmServiceArgs(), "7", "42", REQ, None
    )

    assert loaded.requirement.key == REQ
    assert loaded.requirement_ref == "EXT-1"
    assert loaded.reduced_mode is True
    assert [linked_set.key for linked_set in loaded.linked_sets] == ["1", "3"]
    linked = loaded.linked_sets[0]
    assert linked.key == "1"
    assert linked.spec_key == "spec-1"
    assert linked.description == "Checks the login"
    assert linked.spec_status == "Released"
    assert linked.linked_as_whole is True
    (test_case,) = linked.test_cases
    assert test_case.key == "TC-1"
    assert test_case.parameters == {"user": "bob"}
    assert [(c.phase, c.keyword, c.check, c.arguments) for c in test_case.calls] == [
        ("Setup", "Open login page", False, {}),
        ("TestStep", "Check message", True, {"text": "Locked"}),
    ]


async def test_an_unknown_requirement_raises(monkeypatch):
    monkeypatch.setattr(context_module, "get_requirements", lambda *args: [])

    with pytest.raises(context_module.RequirementNotFoundError, match="'x'"):
        await load_requirement_context(SimpleNamespace(), RmServiceArgs(), "7", "42", "x", None)


def test_a_set_detail_has_all_test_cases_linked_or_not():
    tcs = test_case_set("1", "/A", cases=[case("TC-1", links=[REQ]), case("TC-2")])

    detail = test_case_set_detail(tcs)

    assert [c.key for c in detail.test_cases] == ["TC-1", "TC-2"]
    assert (detail.key, detail.unique_id, detail.description) == ("1", "U-1", "Checks the login")


async def test_an_unassigned_requirement_keeps_the_testbench_key_of_the_trigger(monkeypatch):
    asked = []

    async def _find(conn, rm_args, tov_key, ids):
        asked.append(ids)
        return ExtendedRequirement(
            name="Logout",
            extendedID="EXT-9",
            key={"id": "REQ-9", "version": "3"},
            owner="o",
            status="s",
            priority="p",
            requirement=True,
            description="d",
            documents=None,
            baseline="B",
        )

    monkeypatch.setattr(context_module, "find_rm_requirement", _find)

    with_key = await load_unassigned_requirement(None, RmServiceArgs(), "42", "555", "REQ-9")
    without_key = await load_unassigned_requirement(None, RmServiceArgs(), "42", None, "REQ-9")

    assert asked == [["REQ-9", "555"], ["REQ-9"]]
    assert (with_key.key, with_key.title, with_key.external_ref) == ("555", "Logout", "EXT-9")
    assert without_key.key == "REQ-9"


async def test_an_unassigned_requirement_the_rm_service_does_not_know_is_none(monkeypatch):
    async def _find(*args):
        return None

    monkeypatch.setattr(context_module, "find_rm_requirement", _find)

    assert await load_unassigned_requirement(None, RmServiceArgs(), "42", "555", None) is None
