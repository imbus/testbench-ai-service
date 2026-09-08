"""Tests for the requirement data model and UDF attachment.

The job payload and UDF payload below are verbatim captures from a TestBench
server (project ``VSR-Dreamcar``, baseline serial ``3``), trimmed only by removing
nothing -- they are the real shapes the agent has to parse.
"""

import pytest
from pydantic import TypeAdapter, ValidationError

from testbench_ai_service.agents.requirement.model import (
    Requirement,
    RequirementUdfs,
)
from testbench_ai_service.agents.requirement.utils import (
    attach_udfs,
    iter_requirements,
    parse_loader_job,
)


def _req(serial: str, requirement_serial: str, children=None) -> Requirement:
    return Requirement(
        key={"serial": serial},
        requirementKey={"serial": requirement_serial},
        baselineKey={"serial": "3"},
        id=f"ER_{requirement_serial}",
        extendedID=f"ER_{requirement_serial}",
        name=f"Requirement {requirement_serial}",
        children=children or [],
    )


def _udf_entry(serial: str, **fields: str) -> RequirementUdfs:
    return RequirementUdfs(
        key={"serial": serial},
        value=[
            {"name": name, "type": "ShortTextfield", "value": value}
            for name, value in fields.items()
        ],
    )


JOB_PAYLOAD = {
    "id": "639f6bb2-8ea6-4f38-a229-445a1806e0ec",
    "start": "2026-09-07T14:41:12.907+02:00",
    "completion": {
        "time": "2026-09-07T14:41:12.923+02:00",
        "result": {
            "Right": {
                "key": {"serial": "3"},
                "name": "first draft",
                "type": "CURRENT",
                "repository": "MS Excel",
                "reqProjectName": "VSR-Dreamcar",
                "reProjectKey": {"serial": "3"},
                "lastUpdate": "2015-07-22T13:52:41.000+02:00",
                "children": [
                    {
                        "key": {"serial": "4491"},
                        "requirementKey": {"serial": "475"},
                        "baselineKey": {"serial": "3"},
                        "id": "EF_3100077",
                        "extendedID": "EF_3100077",
                        "name": "1. Business Requirements",
                        "version": "2",
                        "status": "Accepted",
                        "owner": "RE-Manager",
                        "priority": "Essential",
                        "isFolder": False,
                        "children": [
                            {
                                "key": {"serial": "4493"},
                                "requirementKey": {"serial": "479"},
                                "baselineKey": {"serial": "3"},
                                "id": "ER_WHY298",
                                "extendedID": "ER_WHY298",
                                "name": "Allow discount",
                                "version": "2.0",
                                "status": "Submitted",
                                "owner": "RE-Manager",
                                "priority": "Essential",
                                "isFolder": False,
                                "children": [
                                    {
                                        "key": {"serial": "4495"},
                                        "requirementKey": {"serial": "469"},
                                        "baselineKey": {"serial": "3"},
                                        "id": "ER_WHY300",
                                        "extendedID": "ER_WHY300",
                                        "name": "Dealer allows discount",
                                        "version": "3.1",
                                        "status": "Review Complete",
                                        "owner": "RE-Manager",
                                        "priority": "Essential",
                                        "isFolder": False,
                                        "children": [],
                                    }
                                ],
                            }
                        ],
                    }
                ],
                "areRequirementsLoaded": True,
                "loadingError": None,
            }
        },
    },
}

UDF_PAYLOAD = [
    {
        "key": {"serial": "469"},
        "value": [
            {"name": "Business Units", "type": "ShortTextfield", "value": ""},
            {"name": "Owner Priorität", "type": "ShortTextfield", "value": "Even Higher"},
        ],
    },
    {
        "key": {"serial": "479"},
        "value": [
            {"name": "Business Units", "type": "ShortTextfield", "value": "Test,Marketing"},
            {"name": "Owner Priorität", "type": "ShortTextfield", "value": "High"},
        ],
    },
    {
        "key": {"serial": "475"},
        "value": [
            {"name": "Business Units", "type": "ShortTextfield", "value": "n/a"},
            {"name": "Owner Priorität", "type": "ShortTextfield", "value": "n/a"},
        ],
    },
]


class TestParseLoaderJob:
    def test_parses_real_payload(self):
        baseline = parse_loader_job(JOB_PAYLOAD)

        assert baseline.key.serial == "3"
        assert baseline.name == "first draft"
        assert baseline.reqProjectName == "VSR-Dreamcar"
        assert baseline.areRequirementsLoaded is True
        assert baseline.loadingError is None

    def test_nested_children_are_parsed_recursively(self):
        baseline = parse_loader_job(JOB_PAYLOAD)
        all_requirements = list(iter_requirements(baseline.children))

        assert [r.id for r in all_requirements] == [
            "EF_3100077",
            "ER_WHY298",
            "ER_WHY300",
        ]

    def test_raises_on_left_branch(self):
        payload = {
            "id": "job-1",
            "completion": {"result": {"Left": {"message": "RE repository unreachable"}}},
        }

        with pytest.raises(RuntimeError, match="RE repository unreachable"):
            parse_loader_job(payload)

    def test_raises_when_not_completed(self):
        with pytest.raises(RuntimeError, match="has not completed yet"):
            parse_loader_job({"id": "job-1", "completion": None})

    def test_raises_when_neither_branch_present(self):
        with pytest.raises(RuntimeError, match="neither a result nor an error"):
            parse_loader_job({"id": "job-1", "completion": {"result": {}}})

    def test_rejects_requirement_missing_required_field(self):
        with pytest.raises(ValidationError):
            Requirement.model_validate({"key": {"serial": "1"}})


class TestAttachUdfs:
    def test_attaches_udfs_to_matching_requirements(self):
        baseline = parse_loader_job(JOB_PAYLOAD)
        udfs = TypeAdapter(list[RequirementUdfs]).validate_python(UDF_PAYLOAD)

        populated = attach_udfs(baseline.children, udfs)

        by_id = {r.id: r for r in iter_requirements(baseline.children)}
        assert populated == 3
        assert [(f.name, f.value) for f in by_id["ER_WHY300"].udfs] == [
            ("Business Units", ""),
            ("Owner Priorität", "Even Higher"),
        ]
        assert [(f.name, f.value) for f in by_id["ER_WHY298"].udfs] == [
            ("Business Units", "Test,Marketing"),
            ("Owner Priorität", "High"),
        ]

    def test_joins_on_requirement_key_not_node_key(self):
        """Node keys (4491+) and UDF keys (458-479) share no values -- a join on
        ``key.serial`` would silently attach nothing."""
        requirement = _req("4491", "475")

        assert attach_udfs([requirement], [_udf_entry("475", Unit="Sales")]) == 1
        assert [f.value for f in requirement.udfs] == ["Sales"]

        other = _req("4491", "475")
        assert attach_udfs([other], [_udf_entry("4491", Unit="Sales")]) == 0
        assert other.udfs == []

    def test_reaches_requirements_at_every_depth(self):
        deep = _req("1", "10", [_req("2", "20", [_req("3", "30")])])

        populated = attach_udfs(
            [deep],
            [_udf_entry("10", A="a"), _udf_entry("20", B="b"), _udf_entry("30", C="c")],
        )

        assert populated == 3
        assert [f.value for f in deep.children[0].children[0].udfs] == ["c"]

    def test_requirements_without_udfs_keep_empty_list(self):
        matched = _req("1", "10")
        unmatched = _req("2", "20")

        populated = attach_udfs([matched, unmatched], [_udf_entry("10", A="a")])

        assert populated == 1
        assert unmatched.udfs == []

    def test_empty_udf_value_list_is_not_counted_as_populated(self):
        requirement = _req("1", "10")

        populated = attach_udfs([requirement], [RequirementUdfs(key={"serial": "10"}, value=[])])

        assert populated == 0
        assert requirement.udfs == []

    def test_unmatched_udf_entries_are_logged_and_skipped(self, caplog):
        requirement = _req("1", "10")

        with caplog.at_level("WARNING", logger="testbench_ai_service"):
            populated = attach_udfs([requirement], [_udf_entry("999", A="a")])

        assert populated == 0
        assert "999" in caplog.text

    def test_is_idempotent(self):
        baseline = parse_loader_job(JOB_PAYLOAD)
        udfs = TypeAdapter(list[RequirementUdfs]).validate_python(UDF_PAYLOAD)

        attach_udfs(baseline.children, udfs)
        attach_udfs(baseline.children, udfs)

        by_id = {r.id: r for r in iter_requirements(baseline.children)}
        assert len(by_id["ER_WHY300"].udfs) == 2
